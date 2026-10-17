<script setup>
defineProps({ title: String })
defineEmits(['close'])
</script>
<template>
  <div class="modal-mask" @mousedown.self="$emit('close')">
    <div class="modal">
      <header><h2 style="margin:0">{{ title }}</h2><button class="ghost" @click="$emit('close')">✕</button></header>
      <slot />
    </div>
  </div>
</template>
