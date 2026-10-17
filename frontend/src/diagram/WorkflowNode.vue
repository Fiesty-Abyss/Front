<script setup>
// 节点工作流：左侧输入端口、右侧输出端口，中间是参数
import { Handle, Position } from '@vue-flow/core'
import { tint } from './defs'
import { useEdit } from './useEdit'

const props = defineProps(['id', 'data', 'selected'])
const { editing, draft, input, start, commit, onKey } = useEdit(props)
</script>
<template>
  <div class="dn-wf" :class="{ selected }" :style="{ '--c': data.color || '#5b9cf0', '--fill': tint(data.color || '#5b9cf0', 26) }">
    <div class="dn-wf-head" @dblclick.stop="start">
      <span class="dn-wf-dot" />
      <input v-if="editing" ref="input" v-model="draft" class="dn-group-edit nodrag" @blur="commit" @keydown="onKey" />
      <span v-else class="ellip">{{ data.label }}</span>
    </div>
    <div class="dn-wf-ports">
      <div class="dn-wf-col">
        <div v-for="p in data.inputs || []" :key="p.id" class="dn-wf-port in">
          <Handle :id="'in-' + p.id" type="target" :position="Position.Left" class="dn-port" />{{ p.label }}
        </div>
      </div>
      <div class="dn-wf-col right">
        <div v-for="p in data.outputs || []" :key="p.id" class="dn-wf-port out">
          {{ p.label }}<Handle :id="'out-' + p.id" type="source" :position="Position.Right" class="dn-port" />
        </div>
      </div>
    </div>
    <div v-if="(data.fields || []).length" class="dn-wf-fields">
      <div v-for="(f, i) in data.fields" :key="i" class="dn-wf-field"><span class="faint">{{ f.label }}</span><span class="mono ellip">{{ f.value }}</span></div>
    </div>
  </div>
</template>
