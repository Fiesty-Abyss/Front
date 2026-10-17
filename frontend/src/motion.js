// Front 的动效层：全部基于 GSAP（https://gsap.com），遵循 design-motion-principles 的“频率门槛”：
// - 进入页面 / 打开弹窗 / 首次加载列表：一次性的、短（≤ 350ms）的 ease-out 进入；
// - 悬停、点击、键盘操作：不用 GSAP，只有 CSS 的颜色 / 轻微缩放过渡，或者完全不动；
// - 用户开启“减少动态效果”时全部直接显示最终状态。
import { gsap } from 'gsap'

export { gsap }
const mq = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null
export const reduced = () => !!(mq && mq.matches) || document.documentElement.dataset.motion === 'off'

gsap.defaults({ ease: 'power3.out', duration: 0.32 })

/** 页面进入：轻微上移 + 去模糊（“物体对焦”感），离开不做动画。 */
export function enterPage(el, done) {
  if (reduced()) return done?.()
  gsap.fromTo(el, { autoAlpha: 0, y: 8, filter: 'blur(3px)' },
    { autoAlpha: 1, y: 0, filter: 'blur(0px)', duration: 0.34, clearProps: 'filter,transform,opacity,visibility', onComplete: done })
}

/** 弹窗：遮罩淡入，面板从 0.97 缩放（不从 0 开始）。 */
export function enterModal(mask, panel) {
  if (reduced()) return
  gsap.fromTo(mask, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.18, ease: 'power1.out', clearProps: 'opacity,visibility' })
  gsap.fromTo(panel, { autoAlpha: 0, scale: 0.97, y: 6 }, { autoAlpha: 1, scale: 1, y: 0, duration: 0.26, clearProps: 'transform,opacity,visibility' })
}

/** 提示条：进入明显一点，退出更轻。 */
export function enterToast(el, done) {
  if (reduced()) return done()
  gsap.fromTo(el, { autoAlpha: 0, y: 12, filter: 'blur(4px)' }, { autoAlpha: 1, y: 0, filter: 'blur(0px)', duration: 0.3, onComplete: done })
}
export function leaveToast(el, done) {
  if (reduced()) return done()
  gsap.to(el, { autoAlpha: 0, y: 4, duration: 0.16, ease: 'power1.in', onComplete: done })
}

/** 数字从 0 滚到目标值（只在总览首次进入时使用）。 */
export function countUp(el, value) {
  if (!el) return
  if (reduced() || !value) { el.textContent = String(value ?? 0); return }
  const o = { v: 0 }
  gsap.to(o, { v: value, duration: 0.7, ease: 'power2.out', onUpdate: () => { el.textContent = Math.round(o.v).toLocaleString() } })
}

/**
 * v-reveal：容器里第一次出现的子元素（默认 .tile / .card / [data-reveal]）依次淡入。
 * 只对“新出现”的元素做一次，筛选、翻页时新元素同样只动一次；一次最多 24 个，其余直接显示。
 */
const SEL = ':scope > .tile, :scope > .card, :scope > [data-reveal], :scope > .reveal'
function revealNew(el, sel) {
  const fresh = [...el.querySelectorAll(sel || SEL)].filter((n) => !n.__rv)
  if (!fresh.length) return
  fresh.forEach((n) => { n.__rv = true })
  if (reduced()) return
  const anim = fresh.slice(0, 24)
  gsap.fromTo(anim, { autoAlpha: 0, y: 10 },
    { autoAlpha: 1, y: 0, duration: 0.36, stagger: { each: 0.025, from: 'start' }, clearProps: 'transform,opacity,visibility' })
}
export const vReveal = {
  mounted(el, b) { el.__rvSel = b.value; requestAnimationFrame(() => revealNew(el, b.value)) },
  updated(el, b) { requestAnimationFrame(() => revealNew(el, b.value || el.__rvSel)) },
}

/** 侧栏高亮块：在导航项之间滑动（同一个形状贯穿整个导航，而不是每项各自闪烁）。 */
export function movePill(pill, target, container, instant = false) {
  if (!pill || !container) return
  if (!target) { gsap.to(pill, { autoAlpha: 0, duration: 0.12 }); return }
  const c = container.getBoundingClientRect(); const r = target.getBoundingClientRect()
  const y = r.top - c.top + container.scrollTop
  const props = { y, height: r.height, autoAlpha: 1 }
  if (instant || reduced()) gsap.set(pill, props)
  else gsap.to(pill, { ...props, duration: 0.3, ease: 'power3.out', overwrite: true })
}
