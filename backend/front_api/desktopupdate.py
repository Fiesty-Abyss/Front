"""Shell-only pre-install backup. Keep writes paused until owned service stops or cancellation."""
import threading
from fastapi import HTTPException
from . import backups, jobs, maintenance


class Preparation:
    def __init__(self):
        self.lock=threading.RLock()
        self.lease=None
        self.job=None
        self.request_id=0
        self.cancelled_through=0

    def start(self, request_id):
        with self.lock, jobs.manager().lock:
            if request_id<=self.cancelled_through:
                raise HTTPException(409,'update_preparation_cancelled')
            if self.lease:
                if request_id==self.request_id:return self.job.to_dict()
                if request_id<self.request_id:raise HTTPException(409,'update_preparation_outdated')
                self.release(self.request_id)  # A newer owned-shell attempt recovers an orphaned response.
            # Do not strand a queued backup behind workers waiting on our write reservation.
            from .routers.ai import has_active_generations
            if has_active_generations():raise HTTPException(409,'generation_active')
            if any(job.status in ('queued','running') for job in jobs.manager().jobs.values()):
                raise HTTPException(409,'background_jobs_active')
            try:self.lease=maintenance.reserve_writes()
            except RuntimeError:raise HTTPException(409,'writers_busy')
            lease=self.lease
            self.request_id=request_id
            def work(job):
                try:
                    backups.create(job)
                    package=backups.package_for(job.result['backup_id'])
                    manifest,issues=backups.verify(package,job.check)
                    if issues or manifest['status']!='complete':
                        raise RuntimeError('update_backup_incomplete')
                    job.message='正在验证隔离恢复'
                    restore=jobs.Job('full-restore','更新前隔离恢复验证')
                    restore.check=job.check
                    backups.restore(restore,package)
                    job.check()
                    job.result.update(verified=True,restore_verified=True)
                except Exception:
                    self.release(request_id)
                    raise
            try:self.job=jobs.start('full-backup','更新前完整备份与恢复验证',0,work)
            except Exception:
                maintenance.release_writes(lease);self.lease=None
                raise
            return self.job.to_dict()

    def release(self, request_id):
        with self.lock:
            self.cancelled_through=max(self.cancelled_through,request_id)
            if not self.lease or self.request_id!=request_id:
                return False
            if self.job and self.job.status in ('queued','running'):
                self.job.cancel_requested=True
            maintenance.release_writes(self.lease)
            self.lease=None
            return True

    def close(self):
        with self.lock:
            if self.lease:self.release(self.request_id)
