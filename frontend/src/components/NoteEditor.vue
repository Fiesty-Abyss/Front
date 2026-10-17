<script setup>
// 块编辑器：Tiptap（MIT）+ Markdown 存储（tiptap-markdown，MIT）。
// 输入 “/” 打开块菜单；拖入 / 粘贴文件会先存进素材库再嵌入；Ctrl / ⌘ + 点击内部链接跳转。
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import { TaskList } from '@tiptap/extension-task-list'
import { TaskItem } from '@tiptap/extension-task-item'
import { Placeholder } from '@tiptap/extension-placeholder'
import { Image } from '@tiptap/extension-image'
import { TableKit } from '@tiptap/extension-table'
import { Highlight } from '@tiptap/extension-highlight'
import { Markdown } from 'tiptap-markdown'
import { Bold, Italic, Strikethrough, Code, Highlighter, Heading1, Heading2, Heading3, List, ListOrdered, ListChecks, Quote, SquareCode, Minus, Table, Paperclip, Link2, Undo2, Redo2, FileText } from 'lucide-vue-next'
import { api } from '../api'
import { toast } from '../toast'

const props = defineProps({ modelValue: { type: String, default: '' } })
const emit = defineEmits(['update:modelValue', 'pick-asset', 'pick-note'])
const router = useRouter()
const slash = ref(null) // { x, y, q, i }
const host = ref(null)

const BLOCKS = [
  { k: 'h1', label: '一级标题', hint: '#', icon: Heading1, run: (c) => c.toggleHeading({ level: 1 }) },
  { k: 'h2', label: '二级标题', hint: '##', icon: Heading2, run: (c) => c.toggleHeading({ level: 2 }) },
  { k: 'h3', label: '三级标题', hint: '###', icon: Heading3, run: (c) => c.toggleHeading({ level: 3 }) },
  { k: 'ul', label: '无序列表', hint: '-', icon: List, run: (c) => c.toggleBulletList() },
  { k: 'ol', label: '有序列表', hint: '1.', icon: ListOrdered, run: (c) => c.toggleOrderedList() },
  { k: 'todo', label: '待办清单', hint: '[ ]', icon: ListChecks, run: (c) => c.toggleTaskList() },
  { k: 'quote', label: '引用', hint: '>', icon: Quote, run: (c) => c.toggleBlockquote() },
  { k: 'code', label: '代码块', hint: '```', icon: SquareCode, run: (c) => c.toggleCodeBlock() },
  { k: 'hr', label: '分割线', hint: '---', icon: Minus, run: (c) => c.setHorizontalRule() },
  { k: 'table', label: '表格', hint: '3×3', icon: Table, run: (c) => c.insertTable({ rows: 3, cols: 3, withHeaderRow: true }) },
  { k: 'asset', label: '嵌入素材', hint: '图片 / 模型 / 文件', icon: Paperclip, run: null, emit: 'pick-asset' },
  { k: 'note', label: '链接到笔记', hint: '页面', icon: FileText, run: null, emit: 'pick-note' },
]
const filtered = computed(() => { const q = (slash.value?.q || '').toLowerCase(); return BLOCKS.filter((b) => !q || b.label.includes(q) || b.k.includes(q) || b.hint.includes(q)) })

const editor = useEditor({
  content: props.modelValue,
  extensions: [
    StarterKit.configure({ link: { openOnClick: false, autolink: true, HTMLAttributes: { rel: 'noopener noreferrer' } } }),
    TaskList, TaskItem.configure({ nested: true }), Highlight, Image.configure({ allowBase64: false }), TableKit.configure({ table: { resizable: false } }),
    Placeholder.configure({ placeholder: ({ node }) => (node.type.name === 'heading' ? '标题' : '输入 “/” 插入块，或直接把文件拖进来…') }),
    Markdown.configure({ html: false, tightLists: true, linkify: true, transformPastedText: true }),
  ],
  editorProps: {
    attributes: { class: 'prose note-prose', spellcheck: 'false' },
    handleKeyDown: (_view, e) => {
      if (!slash.value) return false
      const n = filtered.value.length
      if (e.key === 'ArrowDown') { slash.value.i = (slash.value.i + 1) % n; return true }
      if (e.key === 'ArrowUp') { slash.value.i = (slash.value.i - 1 + n) % n; return true }
      if (e.key === 'Enter') { if (n) choose(filtered.value[slash.value.i]); return true }
      if (e.key === 'Escape') { slash.value = null; return true }
      return false
    },
    handleClick: (_view, _pos, e) => {
      const a = e.target.closest?.('a[href]')
      if (!a) return false
      const href = a.getAttribute('href')
      if (e.ctrlKey || e.metaKey) {
        if (href.startsWith('/')) router.push(href); else window.open(href, '_blank', 'noopener')
        return true
      }
      return false
    },
    handleDrop: (_view, e) => { const files = [...(e.dataTransfer?.files || [])]; if (!files.length) return false; e.preventDefault(); uploadAndEmbed(files); return true },
    handlePaste: (_view, e) => { const files = [...(e.clipboardData?.files || [])]; if (!files.length) return false; uploadAndEmbed(files); return true },
  },
  onUpdate: ({ editor: ed }) => { emit('update:modelValue', ed.storage.markdown.getMarkdown()); detectSlash(ed) },
  onSelectionUpdate: ({ editor: ed }) => detectSlash(ed),
})

watch(() => props.modelValue, (v) => {
  const ed = editor.value
  if (ed && v !== ed.storage.markdown.getMarkdown()) ed.commands.setContent(v || '', { emitUpdate: false })
})

function detectSlash(ed) {
  const { $from, empty } = ed.state.selection
  if (!empty) { slash.value = null; return }
  const before = $from.parent.textBetween(0, $from.parentOffset, '\n', '\0')
  const m = /(?:^|\s)\/([^\s/]{0,12})$/.exec(before)
  if (!m) { slash.value = null; return }
  const c = ed.view.coordsAtPos($from.pos)
  const box = host.value.getBoundingClientRect()
  slash.value = { x: c.left - box.left, y: c.bottom - box.top + 6, q: m[1], i: slash.value?.q === m[1] ? slash.value.i : 0, from: $from.pos - m[1].length - 1, to: $from.pos }
}
function choose(b) {
  const ed = editor.value
  const s = slash.value
  slash.value = null
  ed.chain().focus().deleteRange({ from: s.from, to: s.to }).run()
  if (b.emit) emit(b.emit)
  else b.run(ed.chain().focus()).run()
}

/** 外部（素材选择器）调用：把素材嵌入到光标处 */
function insertAsset(a) {
  const ed = editor.value
  if (a.width) ed.chain().focus().setImage({ src: `/api/assets/${a.id}/file`, alt: a.title, title: a.title }).run()
  else ed.chain().focus().insertContent([{ type: 'paragraph', content: [{ type: 'text', text: a.title, marks: [{ type: 'link', attrs: { href: `/assets?open=${a.id}` } }] }] }]).run()
}
function insertNoteLink(n) {
  editor.value.chain().focus().insertContent({ type: 'text', text: `${n.icon ? n.icon + ' ' : ''}${n.title}`, marks: [{ type: 'link', attrs: { href: `/notes/${n.id}` } }] }).insertContent(' ').run()
}
async function uploadAndEmbed(files) {
  for (const file of files) {
    const form = new FormData(); form.append('file', file)
    try { insertAsset(await api.upload('/api/assets/upload', form)); toast(`已存入素材库：${file.name}`) } catch (e) {
      const id = e.detail?.asset_id ?? e.body?.detail?.asset_id
      if (id) insertAsset(await api.get(`/api/assets/${id}`)); else toast(e.message, true)
    }
  }
}
function setLink() {
  const prev = editor.value.getAttributes('link').href || ''
  const href = prompt('链接地址（留空移除）', prev)
  if (href === null) return
  if (!href) editor.value.chain().focus().unsetLink().run()
  else editor.value.chain().focus().extendMarkRange('link').setLink({ href }).run()
}
const is = (n, a) => editor.value?.isActive(n, a)
defineExpose({ insertAsset, insertNoteLink, focus: () => editor.value?.commands.focus() })
onBeforeUnmount(() => editor.value?.destroy())
</script>

<template>
  <div ref="host" class="ne">
    <div v-if="editor" class="ne-bar" role="toolbar" aria-label="格式">
      <button class="ghost iconbtn" :class="{ on: is('bold') }" title="加粗 Ctrl+B" @click="editor.chain().focus().toggleBold().run()"><Bold :size="15" /></button>
      <button class="ghost iconbtn" :class="{ on: is('italic') }" title="斜体 Ctrl+I" @click="editor.chain().focus().toggleItalic().run()"><Italic :size="15" /></button>
      <button class="ghost iconbtn" :class="{ on: is('strike') }" title="删除线" @click="editor.chain().focus().toggleStrike().run()"><Strikethrough :size="15" /></button>
      <button class="ghost iconbtn" :class="{ on: is('highlight') }" title="高亮" @click="editor.chain().focus().toggleHighlight().run()"><Highlighter :size="15" /></button>
      <button class="ghost iconbtn" :class="{ on: is('code') }" title="行内代码" @click="editor.chain().focus().toggleCode().run()"><Code :size="15" /></button>
      <button class="ghost iconbtn" :class="{ on: is('link') }" title="链接" @click="setLink"><Link2 :size="15" /></button>
      <span class="sep" />
      <button class="ghost iconbtn" :class="{ on: is('heading', { level: 1 }) }" title="一级标题" @click="editor.chain().focus().toggleHeading({ level: 1 }).run()"><Heading1 :size="15" /></button>
      <button class="ghost iconbtn" :class="{ on: is('heading', { level: 2 }) }" title="二级标题" @click="editor.chain().focus().toggleHeading({ level: 2 }).run()"><Heading2 :size="15" /></button>
      <button class="ghost iconbtn" :class="{ on: is('taskList') }" title="待办" @click="editor.chain().focus().toggleTaskList().run()"><ListChecks :size="15" /></button>
      <button class="ghost iconbtn" :class="{ on: is('bulletList') }" title="列表" @click="editor.chain().focus().toggleBulletList().run()"><List :size="15" /></button>
      <button class="ghost iconbtn" :class="{ on: is('blockquote') }" title="引用" @click="editor.chain().focus().toggleBlockquote().run()"><Quote :size="15" /></button>
      <span class="sep" />
      <button class="ghost small" title="嵌入素材库里的图片、模型或任何文件" @click="emit('pick-asset')"><Paperclip :size="14" />嵌入素材</button>
      <span class="spacer" />
      <button class="ghost iconbtn" title="撤销" :disabled="!editor.can().undo()" @click="editor.chain().focus().undo().run()"><Undo2 :size="15" /></button>
      <button class="ghost iconbtn" title="重做" :disabled="!editor.can().redo()" @click="editor.chain().focus().redo().run()"><Redo2 :size="15" /></button>
    </div>
    <EditorContent :editor="editor" />
    <div v-if="slash && filtered.length" class="slash" :style="{ left: slash.x + 'px', top: slash.y + 'px' }" role="listbox">
      <div class="eyebrow" style="padding:4px 8px 6px">插入块</div>
      <button v-for="(b, i) in filtered" :key="b.k" class="slash-item" :class="{ on: i === slash.i }" role="option" @mousedown.prevent="choose(b)" @mouseenter="slash.i = i">
        <span class="slash-ico"><component :is="b.icon" :size="15" /></span><span>{{ b.label }}</span><span class="faint mono small">{{ b.hint }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.ne { position: relative; }
.ne-bar { position: sticky; top: 84px; z-index: 5; display: flex; align-items: center; gap: 2px; padding: 5px; margin: 0 -6px 10px; border-radius: 12px;
  background: var(--chrome); backdrop-filter: blur(14px); border: 1px solid var(--line); }
.ne-bar .on { color: var(--accent-hi); background: var(--accent-soft); }
.ne-bar .sep { width: 1px; height: 18px; background: var(--line); margin: 0 5px; }
.slash { position: absolute; z-index: 30; width: 250px; max-height: 330px; overflow: auto; padding: 6px; border-radius: 12px; background: var(--panel); border: 1px solid var(--line-strong); box-shadow: var(--shadow-pop); }
.slash-item { display: grid; grid-template-columns: 28px 1fr auto; align-items: center; gap: 8px; width: 100%; padding: 6px 8px; border: 0; background: transparent; border-radius: 8px; text-align: left; color: var(--text); }
.slash-item.on { background: var(--accent-soft); }
.slash-ico { width: 28px; height: 28px; display: grid; place-items: center; border-radius: 8px; background: var(--panel2); color: var(--muted); }
</style>
