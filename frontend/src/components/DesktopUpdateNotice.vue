<script setup>
import { computed, ref, watch } from 'vue'
import Modal from './Modal.vue'
import DesktopUpdates from './DesktopUpdates.vue'
import { updateInfo as info, useDesktopUpdates } from '../desktopUpdates'
useDesktopUpdates(true)
const dismissed = ref(false)
const show = computed(() => !dismissed.value && !info.value.deferred && !!info.value.available_version)
watch(() => info.value.available_version, () => { dismissed.value = false })
</script>
<template><Modal v-if="show" title="Front 有新版可用" @close="dismissed = true"><DesktopUpdates compact /></Modal></template>
