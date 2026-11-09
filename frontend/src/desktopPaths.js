// The official core bridge is already a dependency. Load it only for an explicit native pick.
const purposes = new Set(['discovery_root', 'asset_folder', 'project_folder', 'audio_folder', 'models_folder', 'model_file', 'live2d_folder', 'live2d_archive'])
export const hasNativePaths = () => !!globalThis.window?.__TAURI_INTERNALS__
let core
export async function pickLocalPath(purpose, invoke) {
  if (!purposes.has(purpose)) throw new Error('path_picker_invalid')
  if (!invoke) {
    if (!hasNativePaths()) throw new Error('path_picker_unsupported')
    core ||= await import('@tauri-apps/api/core')
    invoke = core.invoke
  }
  const path = await invoke('desktop_pick_path', { purpose })
  if (path !== null && (typeof path !== 'string' || !path || path.includes('\0'))) throw new Error('path_picker_invalid')
  return path
}
export const pathPickerMessage = code => ({
  path_picker_busy: '另一个文件选择窗口尚未关闭，请先完成或取消。',
  path_picker_unsupported: '此运行环境暂不提供原生路径选择，请填写服务所在电脑的路径。',
  path_picker_forbidden: '当前窗口没有路径选择权限，请回到 Front 桌面主窗口。',
  path_picker_invalid: '未能读取所选路径，请重新选择或手动填写。',
  path_picker_closed: '文件选择窗口已关闭，当前输入保持不变。',
}[code] || '无法打开文件选择窗口，当前输入保持不变；可重试或手动填写路径。')
