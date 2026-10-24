<script setup>
import TagPicker from './TagPicker.vue'
defineProps({form:Object})
</script>
<template><div class="grid"><div class="grid cols-2"><label class="field">来源（人工核对，可留空）<input v-model="form.source" maxlength="2000"/></label><label class="field">版本说明<input v-model="form.version_label" maxlength="100"/></label><label class="field">获取日期<input v-model="form.acquired_on" type="date" @change="form.acquired_on=form.acquired_on||null"/></label><label class="field">星级<input v-model.number="form.stars" type="number" min="0" max="5"/></label><label class="field">喜爱度<input v-model.number="form.preference" type="number" min="0" max="100"/></label><label class="row"><input v-model="form.favorite" type="checkbox"/>收藏</label></div><TagPicker v-model="form.tag_ids"/><label class="field">个人备注<textarea v-model="form.notes" maxlength="30000"/></label></div></template>
<style scoped>.field{min-width:0}.row input[type=checkbox]{width:auto}</style>
