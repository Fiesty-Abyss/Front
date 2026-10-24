<script setup>
import { ref } from 'vue'
import Panel from '../../src/components/DesktopUpdates.vue'
import Notice from '../../src/components/DesktopUpdateNotice.vue'
import { updateAction } from '../../src/desktopUpdates'
const props = defineProps({ model: Object })
const offline = ref(false), bad = ref(false), portable = ref(false)
const narrow = ref(false)
const change = () => {
  Object.assign(props.model.flags, { offline: offline.value, badSignature: bad.value })
  props.model.state.portable = portable.value
  updateAction('status')
}
</script>
<template>
  <div class="grid" style="gap:20px" :style="{ maxWidth: narrow ? '390px' : undefined }">
    <header><h1>软件更新 · 交互验收</h1><p class="muted">生成样本 / Mock 界面；不连接真实 Release，不下载或安装软件。</p></header>
    <div class="row wrap">
      <label><input v-model="offline" type="checkbox" @change="change"> 模拟离线</label>
      <label><input v-model="bad" type="checkbox" @change="change"> 模拟签名失败</label>
      <label><input v-model="portable" type="checkbox" @change="change"> 便携版模拟</label>
      <label><input v-model="narrow" type="checkbox"> 390px 窄容器</label>
    </div>
    <Panel /><Notice />
  </div>
</template>
