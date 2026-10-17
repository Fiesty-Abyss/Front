// 节点内联编辑：双击进入，Enter / 失焦提交，Esc 取消（Shift+Enter 换行）
import { nextTick, ref } from 'vue'
import { useVueFlow } from '@vue-flow/core'

export function useEdit(props, key = 'label') {
  const { updateNodeData } = useVueFlow()
  const editing = ref(false)
  const draft = ref('')
  const input = ref(null)
  async function start() {
    if (props.data?.locked) return
    draft.value = props.data?.[key] ?? ''
    editing.value = true
    await nextTick()
    input.value?.focus(); input.value?.select()
  }
  function commit() {
    if (!editing.value) return
    editing.value = false
    if (draft.value !== (props.data?.[key] ?? '')) updateNodeData(props.id, { [key]: draft.value })
  }
  function onKey(e) {
    e.stopPropagation() // 不触发画布快捷键（删除、复制……）
    if (e.key === 'Escape') { editing.value = false }
    else if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); commit() }
  }
  return { editing, draft, input, start, commit, onKey }
}
