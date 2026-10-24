<script setup>
import { computed, ref, watch } from 'vue'
import { isDesktop, updateInfo as info, updateBusy as busy, updateMessage as message, updateAction as act, useDesktopUpdates } from '../desktopUpdates'
defineProps({ compact: Boolean })
useDesktopUpdates()
const channel = ref('stable')
watch(() => info.value.channel, (value) => { channel.value = value || 'stable' }, { immediate: true })
const phase = computed(() => ({ idle: '等待检查', checking: '正在检查', current: '当前通道没有更新', available: '发现新版', downloading: '正在下载', verifying: '正在验证签名', ready: '签名验证通过', backup: '正在完整备份并验证隔离恢复', installing: '正在启动安装程序', failed: '更新未完成' })[info.value.phase] || '')
const mib = (bytes) => ((bytes || 0) / 1024 ** 2).toFixed(1)
const confirmInstall = ref(false)
</script>
<template>
  <section class="grid desktop-updates" :class="{ card: !compact }" aria-label="软件更新">
    <div class="row"><h2 style="margin:0">软件更新</h2><span class="spacer" /><span v-if="info.version" class="small muted">桌面 {{ info.version }}</span></div>
    <p v-if="!isDesktop" class="muted">网页模式请通过部署流程升级；桌面签名更新在 Windows 客户端中使用。</p>
    <p v-else-if="info.phase === 'loading'" class="muted" role="status">正在读取桌面更新状态…</p>
    <template v-else>
      <p v-if="!info.enabled && !info.error" class="muted">当前预览包未配置更新签名公钥，自动更新尚未启用。正式更新不会由 Commit 或 PR 合并触发。</p>
      <div class="row wrap">
        <label class="row small">更新通道 <select v-model="channel" :disabled="busy" aria-label="更新通道"><option value="stable">稳定版</option><option value="preview">测试版</option></select></label>
        <button :disabled="busy || !info.enabled" @click="act('check', channel)">检查更新</button><span v-if="info.enabled" class="small muted" role="status">{{ phase }}</span>
      </div>
      <p v-if="message" class="update-error" role="status">{{ message }}</p>
      <template v-if="info.available_version">
        <strong>新版 {{ info.available_version }}</strong>
        <pre v-if="info.notes" class="update-notes">{{ info.notes }}</pre>
        <div v-if="['downloading', 'verifying'].includes(info.phase)" class="grid" aria-live="polite">
          <progress :value="info.total ? info.downloaded : undefined" :max="info.total || 1" aria-label="更新下载进度" />
          <span class="small muted">{{ mib(info.downloaded) }} MiB<span v-if="info.total"> / {{ mib(info.total) }} MiB</span> · {{ phase }}</span>
        </div>
        <div v-if="info.phase === 'backup'" class="grid" aria-live="polite">
          <progress :value="info.backup_total ? info.backup_done : undefined" :max="info.backup_total || 1" aria-label="更新前备份进度" />
          <span class="small muted">{{ info.backup_done || 0 }} / {{ info.backup_total || '…' }} · 资料写入暂缓，可取消。</span>
        </div>
        <p v-if="info.saved_filename" class="small muted">已验证文件：{{ info.saved_filename }}（资料目录的 updates 文件夹）</p>
        <p v-if="info.portable" class="small muted">便携版仅下载签名 ZIP。请解压到独立目录并保留原 FrontData，或继续使用同一自定义数据目录；不会覆盖运行中的文件。</p>
        <div class="row wrap">
          <button v-if="info.phase !== 'ready'" :disabled="busy" @click="act('download')">{{ info.portable ? '下载便携新版' : '下载签名更新' }}</button>
          <button v-if="info.phase === 'ready' && !info.portable" class="primary" :disabled="busy" @click="confirmInstall = true">备份并安装</button>
          <button v-if="!busy" class="ghost" @click="act('defer')">稍后提醒（24 小时）</button>
          <button v-if="busy && info.phase !== 'installing'" class="ghost" @click="act('cancel')">取消</button>
        </div>
        <div v-if="confirmInstall" class="card grid" role="group" aria-label="确认安装更新">
          <p>即将验证完整备份，暂缓资料写入并关闭本实例服务，再启动已签名的安装程序。请先保存编辑内容。</p>
          <div class="row"><button class="primary" :disabled="busy" @click="confirmInstall = false; act('install')">确认安装</button><button class="ghost" @click="confirmInstall = false">返回</button></div>
        </div>
      </template>
    </template>
  </section>
</template>
<style scoped>
.desktop-updates { gap: 12px; margin-bottom: 14px; min-width: 0; }
.desktop-updates p { margin: 0; }
.update-notes { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 220px; overflow: auto; margin: 0; font: inherit; font-size: 13px; }
.update-error { color: var(--warn); }
progress { width: 100%; accent-color: var(--accent); }
</style>
