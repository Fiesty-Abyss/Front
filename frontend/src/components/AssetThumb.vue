<script setup>
// 网格里的素材封面：有缩略图就显示缩略图，否则显示类型图标
import { hasThumb, thumb } from '../api'
import KindIcon from './KindIcon.vue'
defineProps({ asset: { type: Object, required: true } })
</script>
<template>
  <div class="img" :class="{ iconic: !hasThumb(asset) }" :style="hasThumb(asset) ? { backgroundImage: `url(${thumb(asset.id, asset.meta?.file?.custom_thumb ? asset.updated_at : '')})` } : {}">
    <KindIcon v-if="!hasThumb(asset)" :asset="asset" />
    <slot />
  </div>
</template>
<style scoped>
.img.iconic { padding: 0; align-items: stretch; }
.img.iconic > :first-child { flex: 1; }
</style>
