<script setup>
import { computed } from 'vue'
import { api } from '../api'
import { toast } from '../toast'

const props = defineProps({ job: Object })
const pct = computed(() => (props.job?.total ? Math.round((props.job.done / props.job.total) * 100) : props.job?.status === 'done' ? 100 : 0))
const STATUS = { queued: '排队中', running: '进行中', done: '已完成', error: '失败', cancelled: '已取消', interrupted: '服务中断' }
async function cancel() { await api.post(`/api/jobs/${props.job.id}/cancel`); toast('已请求取消，当前操作完成后停止') }
</script>
<template>
  <div v-if="job" class="job card">
    <div class="row"><b>{{ job.title }}</b><span class="badge" :class="{ ai: job.status === 'running' }">{{ STATUS[job.status] }}</span><span class="spacer" />
      <span class="small muted">{{ job.done }} / {{ job.total }}</span>
      <button v-if="['queued', 'running'].includes(job.status)" class="ghost small" @click="cancel">取消</button></div>
    <div class="bar"><div :style="{ width: pct + '%' }" :class="job.status" /></div>
    <div v-if="job.message" class="small muted">{{ job.message }}</div>
    <div v-for="(e, i) in job.errors.slice(-3)" :key="i" class="small" style="color:var(--danger, #f87171);white-space:pre-wrap">{{ e.split('\n').slice(-2).join(' ') }}</div>
  </div>
</template>
<style scoped>
.job { display: grid; gap: 8px; padding: 12px 14px; }
.bar { height: 8px; border-radius: 99px; background: #ffffff12; overflow: hidden; }
.bar > div { height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent2)); transition: width .3s; }
.bar > div.error { background: #f87171; }
</style>
