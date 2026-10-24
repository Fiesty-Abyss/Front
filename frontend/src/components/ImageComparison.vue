<script setup>
import {ref,watch} from 'vue'
const props=defineProps({left:String,right:String,leftLabel:{default:'左图'},rightLabel:{default:'右图'}})
const mode=ref('side'),amount=ref(50),natural=ref(false),error=ref('')
watch(()=>[props.left,props.right],()=>{error.value=''})
</script>
<template><section class="grid">
<div class="row"><label>图片对比方式 <select v-model="mode" aria-label="图片对比方式"><option value="side">并排</option><option value="slider">滑杆</option><option value="overlay">透明叠加</option><option value="difference">差异混合</option></select></label><label class="row"><input v-model="natural" type="checkbox"/>原始分辨率</label><a :href="left" target="_blank" rel="noopener">打开左原图</a><a :href="right" target="_blank" rel="noopener">打开右原图</a></div>
<label v-if="['slider','overlay'].includes(mode)" class="field">{{mode==='slider'?'分割位置':'右图不透明度'}} {{amount}}%<input v-model.number="amount" aria-label="对比比例" type="range" min="0" max="100"/></label>
<p v-if="error" class="notice" role="alert">{{error}}</p>
<div class="image-scroll"><div class="comparison" :class="{side:mode==='side',natural,difference:mode==='difference'}"><img :src="left" :alt="leftLabel" @error="error='图片不可用：请检查历史原件或资源归属。'"/><img :src="right" :alt="rightLabel" :class="{layered:mode!=='side'}" :style="mode==='slider'?{clipPath:`inset(0 ${100-amount}% 0 0)`}:mode==='overlay'?{opacity:amount/100}:{}" @error="error='图片不可用：请检查历史原件或资源归属。'"/></div></div><small class="muted">左上角对齐，不同尺寸不自动配准。差异混合只辅助目测，不是语义分析；此视图仅加载两张原图。</small>
</section></template>
<style scoped>
.image-scroll{overflow:auto;max-height:650px;background:repeating-conic-gradient(#7772 0% 25%,transparent 0% 50%) 0 0/20px 20px}.comparison{position:relative;min-height:80px}.comparison img{display:block;max-width:100%;height:auto}.comparison.side{display:grid;grid-template-columns:1fr 1fr;gap:8px}.layered{position:absolute;top:0;left:0;max-height:100%;object-fit:contain;object-position:top left}.comparison.natural{width:max-content}.comparison.natural img{max-width:none}.difference{isolation:isolate;background:#000}.difference .layered{mix-blend-mode:difference}input[type=checkbox]{width:auto}@media(max-width:600px){.comparison.side{grid-template-columns:minmax(0,1fr)}}
</style>
