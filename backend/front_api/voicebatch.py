"""Bounded serial chapter imports on the existing queue and durable cursors."""
from fastapi import HTTPException
from sqlalchemy import select,update,or_
from . import models as m, jobs, voicebooks as book, voiceprojects as vp, voicestudio as vs
from .db import new_session


def status(row):
    value={'id':row.id,'uid':row.uid,'chapter_index':row.chapter_index,'cursor':row.cursor,'end':row.end,
           'status':row.status,'job_id':row.job_id,'error_code':row.error_code}
    job=jobs.get(row.job_id) if row.job_id else None
    if row.status in ('queued','running') and job and job.status in ('cancelled','error','interrupted','done'):
        value.update(status=job.status if job.status!='done' else 'error',error_code='job_ended_before_chapter_commit')
    return value


def reconcile(row):
    """A generic queue cancellation can occur before the runner is entered."""
    job=jobs.get(row.job_id) if row.job_id else None
    if row.status in ('queued','running') and job and job.status in ('cancelled','error','interrupted','done'):
        row.status=job.status if job.status!='done' else 'error'
        row.error_code='job_ended_before_chapter_commit'
        return True
    return False


class ChapterProgress:
    def __init__(self,job):self.job=job;self.result={};self._total=0
    @property
    def total(self):return self._total
    @total.setter
    def total(self,value):self._total=value;self.job.total=self.job.done+value
    def check(self):self.job.check()
    def step(self,message=None):self.job.step(message)


def run(job,uids):
    job.total=0
    outcome='done'
    try:
        for uid in uids:
            job.check()
            with new_session() as session:
                row=session.scalar(select(m.VoiceChapterImport).where(m.VoiceChapterImport.uid==uid))
                if not row or row.status!='queued':raise jobs.Cancelled()
                index=row.chapter_index
            job.message=f'正在导入第{index+1}章（只读正文，不执行AI）'
            jobs.manager().save(job)
            progress=ChapterProgress(job)
            book.run(progress,uid)
            outcome=progress.result.get('status','error')
            if outcome!='done':break
        job.result={'status':outcome,'imports':uids,'speaker_review_required':True,
                    'continuation_required':outcome=='partial'}
    finally:
        # A partial chapter pauses later chapters, preserving novel order. A new
        # explicit request resumes the same cursors; there is no unbounded replay.
        with new_session() as session:
            rows=session.scalars(select(m.VoiceChapterImport).where(m.VoiceChapterImport.uid.in_(uids)))
            for row in rows:
                if row.status in ('queued','running'):
                    row.status='cancelled' if job.cancel_requested else ('waiting' if outcome=='partial' else 'error')
                    row.error_code='waiting_previous_part' if outcome=='partial' else 'batch_stopped'
            session.commit()


def submit(session,project,frame,revision,indices,body):
    if not indices or len(indices)>20 or min(indices)<0 or max(indices)>=len(revision.chapters):
        raise HTTPException(422,'请选择存在的至多20章')
    all_rows=session.scalars(select(m.VoiceChapterImport).where(m.VoiceChapterImport.project_id==project.id,
        or_(m.VoiceChapterImport.chapter_index.in_(indices),m.VoiceChapterImport.status.in_(('queued','running'))))).all()
    for row in all_rows:reconcile(row)
    found={r.chapter_index:r for r in all_rows}
    selected=[found.get(i) for i in indices]
    if all(row and row.status in ('queued','running','done') for row in selected):
        session.commit()
        return selected
    for row in all_rows:
        old=jobs.get(row.job_id) if row.job_id else None
        if row.status in ('queued','running') or (old and old.status in ('queued','running')):
            raise HTTPException(409,'旧任务仍在运行、停止或提交；请等待后续导，避免章节交错或游标重用')
    vs.guard(session,project,body.project_uid,body.expected_project_version)
    pending=[];selected=[]
    for index in sorted(indices):
        row=found.get(index)
        if not row:
            chapter=revision.chapters[index]
            row=m.VoiceChapterImport(project_id=project.id,chapter_index=index,
                cursor=chapter.get('body_start',chapter['start']),end=chapter['end'])
            session.add(row)
        if row.status!='done':
            row.status='queued';row.error_code='';row.job_id=None;pending.append(row)
        selected.append(row)
    vp.touch(session,project,'排队有界章节范围；按章串行，原稿保留')
    session.commit();uids=[r.uid for r in pending]
    try:job=jobs.start('voice-chapter','小说章节草稿（不执行AI）',len(uids),lambda j:run(j,uids))
    except HTTPException:
        for uid in uids:book.terminal(uid,'error','queue_unavailable')
        raise
    session.execute(update(m.VoiceChapterImport).where(m.VoiceChapterImport.uid.in_(uids)).values(job_id=job.id))
    session.commit();session.expire_all()
    return session.scalars(select(m.VoiceChapterImport).where(m.VoiceChapterImport.project_id==project.id,
        m.VoiceChapterImport.chapter_index.in_(indices)).order_by(m.VoiceChapterImport.chapter_index)).all()
