<script setup>
// 分组框：只是画面上的区域与标题，放在其他节点下面
import { NodeResizer } from '@vue-flow/node-resizer'
import { useEdit } from './useEdit'

const props = defineProps(['id', 'data', 'selected'])
const { editing, draft, input, start, commit, onKey } = useEdit(props)
</script>
<template>
  <div class="dn-group" :class="{ selected }" :style="{ '--c': data.color || '#8a8ca3' }">
    <NodeResizer v-if="selected" :min-width="160" :min-height="100" color="var(--accent)" :handle-style="{ width: '8px', height: '8px', borderRadius: '2px' }" :line-style="{ borderColor: 'transparent' }" />
    <input v-if="editing" ref="input" v-model="draft" class="dn-group-edit nodrag" @blur="commit" @keydown="onKey" />
    <div v-else class="dn-group-title" @dblclick.stop="start">{{ data.label }}</div>
  </div>
</template>
