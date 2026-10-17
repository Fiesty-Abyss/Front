import { reactive } from 'vue'

export const toastState = reactive({ msg: '', err: false, timer: null })

export function toast(msg, err = false) {
  toastState.msg = msg
  toastState.err = err
  clearTimeout(toastState.timer)
  toastState.timer = setTimeout(() => (toastState.msg = ''), 2600)
}

export async function guard(fn, okMsg) {
  try {
    const r = await fn()
    if (okMsg) toast(okMsg)
    return r
  } catch (e) {
    toast(e.message || String(e), true)
    throw e
  }
}
