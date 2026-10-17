<script setup>
// 便签：多行文字，可调大小
import { Handle, Position } from '@vue-flow/core'
import { NodeResizer } from '@vue-flow/node-resizer'
import { tint } from './defs'
import { useEdit } from './useEdit'

const props = defineProps(['id', 'data', 'selected'])
const { editing, draft, input, start, commit, onKey } = useEdit(props)
</script>
<template>
  <div class="dn-note" :class="{ selected }" :style="{ '--c': data.color || '#f2c26b', '--fill': tint(data.color || '#f2c26b', 22) }" @dblclick.stop="start">
    <NodeResizer v-if="selected" :min-width="100" :min-height="60" color="var(--accent)" :handle-style="{ width: '8px', height: '8px', borderRadius: '2px' }" :line-style="{ borderColor: 'transparent' }" />
    <textarea v-if="editing" ref="input" v-model="draft" class="dn-edit nodrag nowheel" @blur="commit" @keydown="onKey" />
    <div v-else class="dn-note-text">{{ data.label }}</div>
    <Handle v-for="[p, hid] in [[Position.Top, 't'], [Position.Right, 'r'], [Position.Bottom, 'b'], [Position.Left, 'l']]" :id="hid" :key="hid" type="source" :position="p" class="dn-h" />
  </div>
</template>
