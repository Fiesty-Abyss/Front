<script setup>
import { onMounted, ref } from 'vue'
import { X } from 'lucide-vue-next'
import { enterModal } from '../motion'
defineProps({ title: String, wide: Boolean })
const emit = defineEmits(['close'])
const mask = ref(null)
const panel = ref(null)
onMounted(() => { enterModal(mask.value, panel.value); panel.value?.focus() })
</script>
<template>
  <div ref="mask" class="modal-mask" @mousedown.self="emit('close')" @keydown.esc="emit('close')">
    <div ref="panel" class="modal" :class="{ wide }" tabindex="-1" role="dialog" :aria-label="title">
      <header><h2 style="margin:0">{{ title }}</h2><button class="ghost iconbtn" aria-label="关闭" @click="emit('close')"><X :size="16" /></button></header>
      <slot />
    </div>
  </div>
</template>
