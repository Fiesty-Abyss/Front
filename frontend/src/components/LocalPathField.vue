<script>
let sequence = 0
</script>
<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { hasNativePaths, pickLocalPath, pathPickerMessage } from '../desktopPaths'
const props = defineProps({modelValue: {type:String,default:''}, label:String, purpose:String, alternatePurpose:String, disabled:Boolean, required:Boolean, placeholder:String, mono:Boolean})
const emit = defineEmits(['update:modelValue', 'enter'])
const id = `front-local-path-${++sequence}`, native = hasNativePaths(), busy = ref(false), error = ref('')
let disposed = false
onBeforeUnmount(() => { disposed = true })
async function pick(purpose) {
  if (busy.value || props.disabled) return
  busy.value = true; error.value = ''
  const previous = props.modelValue
  try {
    const selected = await pickLocalPath(purpose)
    // Cancelling, leaving, changing records or typing meanwhile must not replace the current input.
    if (!disposed && !props.disabled && props.modelValue === previous && selected !== null) emit('update:modelValue', selected)
  } catch (e) { if (!disposed) error.value = pathPickerMessage(typeof e === 'string' ? e : e.message) }
  finally { if (!disposed) busy.value = false }
}
</script>
<template>
  <div class="field local-path-field">
    <label :for="id">{{label}}</label>
    <div class="local-path-row">
      <input :id="id" :value="modelValue" :required="required" :disabled="disabled" :placeholder="placeholder" :class="{mono}" @input="emit('update:modelValue',$event.target.value)" @keyup.enter="emit('enter')"/>
      <button v-if="native" type="button" :disabled="busy||disabled" @click="pick(purpose)">{{busy?'正在选择…':purpose.endsWith('_file')?'选择文件':'选择文件夹'}}</button>
      <button v-if="native&&alternatePurpose" type="button" :disabled="busy||disabled" @click="pick(alternatePurpose)">选择压缩包</button>
    </div>
    <small v-if="error" role="alert" class="notice">{{error}}</small>
  </div>
</template>
<style scoped>
.local-path-field{min-width:0}.local-path-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.local-path-row input{flex:1 1 220px;min-width:0;width:auto}.local-path-row button{flex:0 0 auto}.notice{margin:0;overflow-wrap:anywhere}
</style>
