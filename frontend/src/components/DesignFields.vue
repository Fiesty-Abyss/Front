<script setup>
import { computed, ref } from 'vue'
const props=defineProps({modelValue:{type:Object,default:()=>({})},prefix:{type:String,default:'角色'},defaults:{type:Array,default:()=>['年龄或年龄段','外貌','身材与体型','发型','瞳色','服装与配饰','性格','背景设定','能力']}})
const emit=defineEmits(['update:modelValue'])
const custom=ref('')
const keys=computed(()=>[...new Set([...props.defaults,...Object.keys(props.modelValue)])])
function set(key,value){emit('update:modelValue',{...props.modelValue,[key]:value})}
function remove(key){emit('update:modelValue',Object.fromEntries(Object.entries(props.modelValue).filter(([k])=>k!==key)))}
function add(){const key=custom.value.trim();if(!key||key.length>80)return;set(key,props.modelValue[key]||'');custom.value=''}
</script>
<template><div class="grid"><p class="small muted">字段均可留空；自定义字段保存在当前设计草稿中。</p><div class="grid cols-2"><label v-for="key in keys" :key="key" class="field">{{key}}<textarea :aria-label="prefix+' · '+key" :value="modelValue[key]||''" maxlength="10000" @input="set(key,$event.target.value)"/><button v-if="!defaults.includes(key)" class="small" @click="remove(key)">移除此字段</button></label></div><div class="row"><input v-model="custom" :aria-label="prefix+' · 新字段名称'" placeholder="自定义字段名称" maxlength="80"/><button type="button" :disabled="!custom.trim()" @click="add">添加字段</button></div></div></template>
<style scoped>textarea{min-height:72px;resize:vertical}.field{min-width:0}</style>
