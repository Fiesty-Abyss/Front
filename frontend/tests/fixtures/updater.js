// Development fixture only. Not imported by the production build. No real downloads or installs.
const state = { enabled: true, version: '0.7.0-preview.1', portable: false, channel: 'stable', phase: 'idle', deferred: false }
const flags = { offline: false, badSignature: false, cancelled: false }
window.__TAURI_INTERNALS__ = { invoke: async (_command, { action, channel }) => {
  if (action === 'check') Object.assign(state, { available_version: null, notes: null, saved_filename: null }, flags.offline ? { phase: 'failed', error: 'update_check_failed' } : { phase: 'available', error: null, channel: channel || state.channel, deferred: false, available_version: '9.9.0', notes: '生成样本更新说明：改善预览资源释放。\n此为 Mock 界面验收，不是 GitHub Release。' })
  if (action === 'defer') state.deferred = true
  if (action === 'cancel') flags.cancelled = true
  if (action === 'download') {
    flags.cancelled = false; state.error = null; state.phase = 'downloading'; state.downloaded = 0; state.total = 4 * 1024 ** 2
    await new Promise((resolve) => { const timer = setInterval(() => {
      state.downloaded = Math.min(state.total, state.downloaded + 128 * 1024)
      if (flags.cancelled || state.downloaded >= state.total) { clearInterval(timer); resolve() }
    }, 80) })
    Object.assign(state, flags.cancelled ? { phase: 'failed', error: 'update_cancelled' } : flags.badSignature ? { phase: 'failed', error: 'update_signature_or_download_failed' } : { phase: 'ready', saved_filename: state.portable ? 'Generated-preview.zip' : 'Generated-setup.exe' })
  }
  if (action === 'install') Object.assign(state, { phase: 'failed', error: 'update_install_failed' })
  return { ...state }
} }
const [{ createApp }, { default: Fixture }] = await Promise.all([import('vue'), import('./UpdaterFixture.vue')])
createApp(Fixture, { model: { state, flags } }).mount('#fixture')
