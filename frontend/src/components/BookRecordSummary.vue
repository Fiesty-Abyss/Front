<script setup>
import { computed } from 'vue'
import { bookRecordKind } from '../metadataDisplay'
const props=defineProps({item:Object})
const type=computed(()=>bookRecordKind(props.item))
const text=value=>Array.isArray(value)?value.filter(v=>typeof v==='string').join('、'):typeof value==='string'?value:''
const fields=computed(()=>type.value?[
  ['作者姓名',text(props.item.authors)],['ISBN-10',text(props.item.isbn_10)],['ISBN-13',text(props.item.isbn_13)],
  ['版次说明',text(props.item.edition_name)],['出版商',text(props.item.publisher)],
  ['出版日期（来源原文）',text(props.item.publish_date)||text(props.item.date)],
  ['语言代码',text(props.item.languages)],['所属作品 ID',text(props.item.work_ids)],
]:[])
</script>
<template>
  <section v-if="type" class="book-record" aria-label="图书版次核对">
    <p><b>{{type}}</b> · <span class="mono">{{item.sid}}</span></p>
    <dl><template v-for="[label,value] in fields" :key="label"><dt>{{label}}</dt><dd>{{value||'来源未提供'}}</dd></template></dl>
    <p class="small muted">作品 ID 与版次 ID 分别保留；同名或高匹配度不代表同一译本。语言保持来源代码，作者或译者不明时不推断。核对后再勾选应用字段。</p>
  </section>
</template>
<style scoped>
.book-record{min-width:0;border-top:1px solid var(--line);padding-top:10px}.book-record dl{display:grid;grid-template-columns:minmax(130px,.5fr) minmax(0,1fr);gap:8px 16px;margin:0}.book-record dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}.book-record dt{color:var(--muted)}@media(max-width:500px){.book-record dl{grid-template-columns:minmax(0,1fr);gap:4px}.book-record dd{margin-bottom:8px}}
</style>
