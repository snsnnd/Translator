<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'

const files = ref([])
const loading = ref(true)
const preview = ref(null)
const error = ref('')

function kind(f) {
  if (f.name.includes('zh.mono')) return { label: '纯中文译文', cls: 'bg-teal-500/15 text-teal-400' }
  if (f.name.includes('zh.dual')) return { label: '双语对照', cls: 'bg-blue-500/15 text-blue-400' }
  if (f.name.includes('glossary')) return { label: '术语表', cls: 'bg-violet-500/15 text-violet-400' }
  if (f.name.includes('目录')) return { label: '目录附件', cls: 'bg-amber-500/15 text-amber-400' }
  return { label: '文件', cls: 'bg-zinc-500/15 text-zinc-400' }
}
function fmtSize(n) {
  if (n > 1 << 30) return (n / (1 << 30)).toFixed(2) + ' GB'
  if (n > 1 << 20) return (n / (1 << 20)).toFixed(1) + ' MB'
  return (n / 1024).toFixed(0) + ' KB'
}
function fmtDate(ts) { return new Date(ts * 1000).toLocaleString('zh-CN', { hour12: false }) }
// rel 是相对 output/ 的路径(可能含书名文件夹), 逐段编码
const fileUrl = (rel) => '/output-files/' + rel.split('/').map(encodeURIComponent).join('/')

async function load() {
  loading.value = true
  const data = await api.output()
  files.value = data.files
  loading.value = false
}

async function deleteFile(f) {
  if (!confirm(`确定删除产物？\n${f.rel}`)) return
  try {
    await api.deleteOutput(f.rel)
    if (preview.value === f.rel) preview.value = null
    load()
  } catch (e) { error.value = e.message }
}

onMounted(load)
</script>

<template>
  <div class="max-w-5xl mx-auto px-8 py-10">
    <h2 class="text-2xl font-bold mb-1">产物</h2>
    <p class="text-sm text-zinc-500 mb-8">output/ 目录的译文成品与附件</p>

    <div v-if="error" class="mb-6 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">{{ error }}</div>

    <div v-if="!loading && files.length === 0" class="text-center py-24 text-zinc-500">还没有产物，先去翻译一本书吧</div>

    <div v-if="preview" class="mb-8 rounded-2xl border border-zinc-800 overflow-hidden bg-zinc-900/40">
      <div class="flex items-center justify-between px-4 py-2.5 border-b border-zinc-800">
        <p class="text-sm truncate mr-4">{{ preview }}</p>
        <div class="flex gap-2 shrink-0">
          <a :href="fileUrl(preview)" target="_blank" class="px-3 py-1.5 rounded-lg border border-zinc-700 text-xs hover:border-zinc-500">新窗口打开</a>          <button @click="preview = null" class="px-3 py-1.5 rounded-lg border border-zinc-700 text-xs hover:border-zinc-500">关闭预览</button>
        </div>
      </div>
      <iframe :src="fileUrl(preview)" class="w-full h-[70vh] bg-zinc-950"></iframe>
    </div>

    <div class="space-y-3">
      <div v-for="f in files" :key="f.rel"
        class="flex items-center gap-4 px-5 py-4 rounded-xl border border-zinc-800 bg-zinc-900/40 hover:border-zinc-700 transition-colors">
        <div class="w-10 h-12 shrink-0 rounded bg-zinc-800 flex items-center justify-center text-lg">
          {{ f.name.endsWith('.csv') ? '📊' : '📄' }}
        </div>
        <div class="flex-1 min-w-0">
          <p class="font-medium truncate text-sm" :title="f.rel">{{ f.name }}</p>
          <p class="text-xs text-zinc-500 mt-0.5">{{ f.rel.includes('/') ? f.rel.split('/')[0] + ' · ' : '' }}{{ fmtSize(f.size) }} · {{ fmtDate(f.mtime) }}</p>
        </div>
        <span class="px-2.5 py-0.5 rounded-full text-xs shrink-0" :class="kind(f).cls">{{ kind(f).label }}</span>
        <button v-if="f.name.endsWith('.pdf')" @click="preview = f.rel"
          class="px-3 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-500 text-xs transition-colors shrink-0">预览</button>
        <a :href="fileUrl(f.rel)" :download="f.name"
          class="px-3 py-1.5 rounded-lg bg-teal-600/90 hover:bg-teal-500 text-xs font-medium transition-colors shrink-0">下载</a>
        <button @click="deleteFile(f)"
          class="w-7 h-7 rounded-lg flex items-center justify-center text-zinc-600 hover:text-red-400 hover:bg-red-500/10 transition-colors shrink-0"
          title="删除产物">🗑</button>
      </div>
    </div>
  </div>
</template>
