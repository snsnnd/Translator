<script setup>
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import SponsorPopup from './components/SponsorPopup.vue'

const route = useRoute()
const nav = [
  { to: '/', label: '书架', icon: '📚' },
  { to: '/progress', label: '任务进度', icon: '⏳' },
  { to: '/output', label: '产物', icon: '📄' },
  { to: '/toolbox', label: '工具箱', icon: '🧰' },
  { to: '/settings', label: '设置', icon: '⚙️' },
]
const collapsed = ref(false)
</script>

<template>
  <div class="flex h-screen">
    <aside class="w-52 shrink-0 border-r border-zinc-800 bg-zinc-900/50 flex flex-col">
      <div class="px-5 py-5">
        <h1 class="text-lg font-bold tracking-tight">PDF 翻译器</h1>
        <p class="text-xs text-zinc-500 mt-0.5">英文 → 中文 · 保留排版</p>
      </div>
      <nav class="flex-1 px-3 space-y-1">
        <RouterLink
          v-for="n in nav" :key="n.to" :to="n.to"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors"
          :class="route.path === n.to
            ? 'bg-teal-600/15 text-teal-400 font-medium'
            : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'"
        >
          <span class="text-base">{{ n.icon }}</span>{{ n.label }}
        </RouterLink>
      </nav>
      <div class="px-5 py-4 text-[11px] text-zinc-600 leading-relaxed">
        BabelDOC 内核 · GLM 模型<br/>本地单用户工具
      </div>
    </aside>
    <main class="flex-1 overflow-y-auto">
      <RouterView />
    </main>
    <SponsorPopup />
  </div>
</template>
