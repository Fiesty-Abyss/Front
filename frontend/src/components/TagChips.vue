<script setup>
import { LABELS } from '../api'
defineProps({ tags: { type: Array, default: () => [] }, showCat: Boolean })
</script>
<template>
  <span class="row" style="gap:5px">
    <span v-for="t in tags" :key="t.id" class="chip"><span v-if="showCat" class="cat">{{ LABELS.tagCategory[t.category] ?? t.category }}·</span>{{ t.name }}</span>
  </span>
</template>
