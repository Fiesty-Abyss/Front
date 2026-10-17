<script setup>
defineOptions({ name: 'EntryTree' })
defineProps({ nodes: Array, depth: { type: Number, default: 0 } })
defineEmits(['open'])
</script>
<template>
  <div v-for="n in nodes" :key="n.id">
    <div class="tree-row" :style="{ paddingLeft: depth * 22 + 8 + 'px' }" @click="$emit('open', n)">
      <span class="muted">{{ n.children.length ? '▾' : '·' }}</span>
      <b>{{ n.name }}</b>
      <span class="small muted">{{ n.summary }}</span>
      <span class="spacer" />
      <span v-if="n.links.length" class="badge">{{ n.links.length }} 位角色</span>
    </div>
    <EntryTree v-if="n.children.length" :nodes="n.children" :depth="depth + 1" @open="$emit('open', $event)" />
  </div>
</template>
<style scoped>
.tree-row { display: flex; gap: 10px; align-items: center; padding: 8px; border-radius: 8px; cursor: pointer; }
.tree-row:hover { background: var(--panel2); }
</style>
