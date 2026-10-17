<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { LABELS, Tags } from '../api'
import { guard } from '../toast'

const tags = ref([])
const form = reactive({ name: '', category: 'custom' })
async function load() { tags.value = (await Tags.list({ limit: 500 })).items }
onMounted(load)
const grouped = computed(() => { const g = {}; for (const t of tags.value) (g[t.category] ??= []).push(t); return g })
async function add() { await guard(() => Tags.create({ ...form }), '已添加'); form.name = ''; load() }
async function rename(t) { const name = prompt('新名称', t.name); if (name && name !== t.name) { await guard(() => Tags.update(t.id, { name }), '已重命名'); load() } }
async function remove(t) { if (confirm(`删除标签「${t.name}」？`)) { await guard(() => Tags.remove(t.id), '已删除'); load() } }
</script>
<template>
  <form class="row card" style="margin-bottom:14px" @submit.prevent="add">
    <select v-model="form.category" style="width:140px"><option v-for="(l, k) in LABELS.tagCategory" :key="k" :value="k">{{ l }}</option></select>
    <input v-model="form.name" placeholder="标签名" style="max-width:240px" required /><button class="primary">添加标签</button>
    <span class="small muted">标签按分类组成筛选维度：性别、媒介（动漫/游戏）、来源作品、画风、类型……</span>
  </form>
  <div class="grid cols-3">
    <div v-for="(list, cat) in grouped" :key="cat" class="card">
      <h2 style="margin-top:0">{{ LABELS.tagCategory[cat] ?? cat }}</h2>
      <div class="row" style="gap:6px"><span v-for="t in list" :key="t.id" class="chip">{{ t.name }}<a class="small" title="重命名" @click="rename(t)">✎</a><a class="small" title="删除" @click="remove(t)">✕</a></span></div>
    </div>
  </div>
</template>
