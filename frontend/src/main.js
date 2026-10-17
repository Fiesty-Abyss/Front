import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'
import { vReveal } from './motion'
import Ico from './components/Ico.vue'

const routes = [
  { path: '/', component: () => import('./views/Dashboard.vue'), meta: { title: '总览' } },
  { path: '/assets', component: () => import('./views/Assets.vue'), meta: { title: '素材库' } },
  { path: '/notes/:id?', component: () => import('./views/Notes.vue'), meta: { title: '笔记本' } },
  { path: '/characters', component: () => import('./views/Characters.vue'), meta: { title: '角色百科' } },
  { path: '/characters/:id', component: () => import('./views/CharacterDetail.vue'), meta: { title: '角色详情' } },
  { path: '/worlds', component: () => import('./views/Worlds.vue'), meta: { title: '世界观' } },
  { path: '/graph', component: () => import('./views/Graph.vue'), meta: { title: '关系网' } },
  { path: '/works', component: () => import('./views/Works.vue'), meta: { title: '作品 / CG' } },
  { path: '/import', component: () => import('./views/Import.vue'), meta: { title: '批量导入' } },
  { path: '/collections', component: () => import('./views/Collections.vue'), meta: { title: '收藏集' } },
  { path: '/read/:id', component: () => import('./views/Reader.vue'), meta: { title: '阅读', bare: true } },
  { path: '/prompts', component: () => import('./views/Prompts.vue'), meta: { title: '提示词库' } },
  { path: '/models', component: () => import('./views/Models.vue'), meta: { title: 'SD 模型库' } },
  { path: '/snippets', component: () => import('./views/Snippets.vue'), meta: { title: '提示词片段' } },
  { path: '/generate', component: () => import('./views/Generate.vue'), meta: { title: '出图' } },
  { path: '/cards', component: () => import('./views/Cards.vue'), meta: { title: '角色卡' } },
  { path: '/chat', component: () => import('./views/Chat.vue'), meta: { title: 'AI 对话' } },
  { path: '/lorebooks', component: () => import('./views/Lorebooks.vue'), meta: { title: '世界书' } },
  { path: '/extract', component: () => import('./views/Extract.vue'), meta: { title: '从小说抽取角色' } },
  { path: '/settings', component: () => import('./views/Settings.vue'), meta: { title: '设置' } },
  { path: '/tags', component: () => import('./views/Tags.vue'), meta: { title: '标签' } },
  { path: '/search', component: () => import('./views/Search.vue'), meta: { title: '搜索' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: (to, from, saved) => saved || (to.hash ? new Promise((r) => setTimeout(() => r({ el: to.hash, top: 90, behavior: 'smooth' }), 400)) : { top: 0 }),
})
router.afterEach((to) => { document.title = `${to.meta.title ?? ''} · Front` })

const app = createApp(App).use(router).directive('reveal', vReveal).component('Ico', Ico)
router.isReady().then(() => app.mount('#app'))
