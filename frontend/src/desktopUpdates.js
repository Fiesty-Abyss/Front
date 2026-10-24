import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

export const isDesktop = !!window.__TAURI_INTERNALS__
export const updateInfo = ref({ enabled: false, phase: isDesktop ? 'loading' : 'idle', channel: 'stable' })
const pending = ref(false)
const activePhases = ['checking', 'downloading', 'verifying', 'backup', 'installing']
export const updateBusy = computed(() => pending.value || activePhases.includes(updateInfo.value.phase))
let api, timer, subscribers = 0, checked = false
const messages = {
  update_not_configured: '当前测试包未配置更新签名公钥，自动更新尚未启用。',
  update_check_failed: '检查更新失败，可能尚无对应发布或网络不可用；本地资料仍可使用。',
  update_source_invalid: '更新来源不符合本仓库的安全规则。',
  update_signature_or_download_failed: '下载或签名校验失败，更新未安装，请重试。',
  update_too_large: '更新包超过 256 MiB 安全上限，已停止下载。',
  update_background_busy: '仍有后台任务或资料写入，请等待结束后再安装。',
  update_backup_failed: '更新前备份或隔离恢复验证失败，已停止安装。',
  update_backup_timeout: '备份等待超时，未安装更新；请检查后台任务与磁盘空间。',
  update_cancelled: '已取消，未安装更新。',
  update_not_running: '当前没有进行中的更新操作。',
  update_busy: '另一项更新操作正在处理，请稍候。',
  update_install_in_progress: '安装已经开始，请留意安装窗口；Front 此时无法取消。',
  update_portable_manual: '便携版请下载新版到独立目录，保留原 FrontData 或继续使用自定义数据目录。',
  update_incompatible: '更新通道、平台或数据兼容声明不匹配，已停止更新。',
  update_compatibility_missing: '更新缺少数据兼容声明，已停止更新。',
  update_version_invalid: '更新版本不符合当前通道，已停止更新。',
  update_storage_failed: '无法保存更新，请检查资料目录权限及磁盘空间。',
  update_preferences_failed: '无法保存更新偏好，请检查资料目录权限。',
  update_install_failed: '无法启动安装程序，资料已保留；可重试或使用已下载的安装包。',
  update_install_failed_restarted: '上次未能启动安装程序，Front 已重新启动并保留资料。',
}
export const updateMessage = computed(() => messages[updateInfo.value.error] || (updateInfo.value.error ? '桌面更新暂不可用，请重启或稍后重试。' : ''))
async function invoke(action, channel) {
  api ||= await import('@tauri-apps/api/core')
  return api.invoke('desktop_update', { action, channel: channel || null })
}
async function poll() {
  clearTimeout(timer)
  if (!subscribers || !isDesktop || !updateBusy.value) return
  try { updateInfo.value = await invoke('status') } catch { /* final operation reports the error */ }
  if (subscribers && updateBusy.value) timer = setTimeout(poll, 500)
}
export async function updateAction(action, channel) {
  if (!isDesktop) return
  if (action !== 'cancel') pending.value = true
  const starting = { check: 'checking', download: 'downloading', install: 'backup' }[action]
  if (starting) updateInfo.value = { ...updateInfo.value, phase: starting }
  if (subscribers && !timer) timer = setTimeout(poll, 500)
  try { updateInfo.value = await invoke(action, channel) }
  catch (code) { updateInfo.value = { ...updateInfo.value, phase: 'failed', error: typeof code === 'string' && messages[code] ? code : 'update_status_unavailable' } }
  finally {
    if (action !== 'cancel') pending.value = false
    clearTimeout(timer); timer = null
    if (subscribers && updateBusy.value) timer = setTimeout(poll, 500)
  }
}
export function useDesktopUpdates(automatic = false) {
  onMounted(async () => {
    subscribers++
    if (!isDesktop) return
    try {
      updateInfo.value = await invoke('status')
      if (automatic && !checked) {
        checked = true
        if (updateInfo.value.enabled && !updateInfo.value.deferred && !updateInfo.value.error) await updateAction('check')
      }
    } catch { updateInfo.value = { ...updateInfo.value, error: 'update_status_unavailable' } }
  })
  onBeforeUnmount(() => { if (--subscribers === 0) { clearTimeout(timer); timer = null } })
}
