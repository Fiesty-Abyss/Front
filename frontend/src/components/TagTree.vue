<script setup>
defineOptions({ name: 'TagTree' })
defineProps({ nodes: Array, usage: Object, depth: { type: Number, default: 0 } })
defineEmits(['open'])
</script>
<template>
  <div v-for="t in nodes" :key="t.id">
    <div class="tag-row" :style="{ paddingLeft: depth * 20 + 6 + 'px' }" @click="$emit('open', t)">
      <span class="muted small">{{ t.children.length ? '▾' : '·' }}</span>
      <span class="dot" :style="{ background: t.color || 'var(--muted)' }" />
      <b>{{ t.name }}</b>
      <span v-if="t.aliases.length" class="small muted" :title="'别名：' + t.aliases.join('、')">= {{ t.aliases.join(' / ') }}</span>
      <span class="spacer" />
      <span class="badge" :title="`直接使用 ${usage[t.id]?.direct ?? 0} 次，含子标签共 ${usage[t.id]?.total ?? 0} 个条目`">{{ usage[t.id]?.total ?? 0 }}<template v-if="t.children.length && (usage[t.id]?.direct ?? 0) !== (usage[t.id]?.total ?? 0)"> · 直接 {{ usage[t.id]?.direct ?? 0 }}</template></span>
    </div>
    <TagTree v-if="t.children.length" :nodes="t.children" :usage="usage" :depth="depth + 1" @open="$emit('open', $event)" />
  </div>
</template>
<style scoped>
.tag-row { display: flex; align-items: center; gap: 7px; padding: 5px 6px; border-radius: 7px; cursor: pointer; }
.tag-row:hover { background: var(--panel2); }
.dot { width: 9px; height: 9px; border-radius: 50%; flex: none; }
</style>
