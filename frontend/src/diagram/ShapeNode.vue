<script setup>
// 流程图形状节点：矩形 / 胶囊 / 菱形 / 平行四边形 / 文档 / 圆柱 / 六边形 / 圆；四边都能连线
import { computed, inject } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import { NodeResizer } from '@vue-flow/node-resizer'
import { Link2 } from 'lucide-vue-next'
import { tint } from './defs'
import { useEdit } from './useEdit'

const props = defineProps(['id', 'data', 'selected'])
const openLink = inject('openLink', () => {})
const { editing, draft, input, start, commit, onKey } = useEdit(props)
const color = computed(() => props.data.color || '#9a6ad0')
const shape = computed(() => props.data.shape || 'rect')
const svgShape = computed(() => ['diamond', 'parallelogram', 'document', 'cylinder', 'hexagon'].includes(shape.value))
const PATHS = {
  diamond: 'M50,1 L99,50 L50,99 L1,50 Z',
  parallelogram: 'M14,1 L99,1 L86,99 L1,99 Z',
  hexagon: 'M12,1 L88,1 L99,50 L88,99 L12,99 L1,50 Z',
  document: 'M1,1 L99,1 L99,84 C75,70 60,104 35,92 C20,85 10,86 1,90 Z',
  cylinder: 'M1,12 C1,-3 99,-3 99,12 L99,88 C99,103 1,103 1,88 Z',
}
</script>
<template>
  <div class="dn-shape" :class="[shape, { selected, svg: svgShape }]" :style="{ '--c': color, '--fill': tint(color, 18) }" @dblclick.stop="start">
    <NodeResizer v-if="selected && !data.locked" :min-width="48" :min-height="36" color="var(--accent)" :handle-style="{ width: '8px', height: '8px', borderRadius: '2px' }" :line-style="{ borderColor: 'transparent' }" />
    <svg v-if="svgShape" class="dn-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <path :d="PATHS[shape]" vector-effect="non-scaling-stroke" />
      <path v-if="shape === 'cylinder'" d="M1,12 C1,27 99,27 99,12" fill="none" vector-effect="non-scaling-stroke" />
    </svg>
    <textarea v-if="editing" ref="input" v-model="draft" class="dn-edit nodrag nowheel" rows="2" @blur="commit" @keydown="onKey" />
    <div v-else class="dn-label">{{ data.label }}</div>
    <button v-if="data.link" class="dn-link nodrag" :title="'打开 ' + data.link" @click.stop="openLink(data.link)"><Link2 :size="11" /></button>
    <Handle v-for="[p, hid] in [[Position.Top, 't'], [Position.Right, 'r'], [Position.Bottom, 'b'], [Position.Left, 'l']]" :id="hid" :key="hid" type="source" :position="p" class="dn-h" />
  </div>
</template>
