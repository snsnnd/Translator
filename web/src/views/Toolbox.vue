<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { api } from '../api'
import PhaseBadge from '../components/PhaseBadge.vue'

const books = ref([])
const outputs = ref([])
const jobs = ref([])
const error = ref('')
let timer = null

// build_final
const bfBook = ref('')
const bfFont = ref('serif')
const bfNoWatermark = ref(true)
const bfKeepLayer = ref(false)
const bfDryRun = ref(false)

// rewrite_toc / bookmarks
const rtBook = ref('')
const rtTranslated = ref('')
const rtToc = ref('')
const rtIndex = ref('')
const bmBook = ref('')
const bmTranslated = ref('')

const dryRunResult = ref(null)

async function load() {
  const [b, o, j] = await Promise.all([api.books(), api.output(), api.jobs()])
  books.value = b.books
  outputs.value = o.files.filter(f => f.name.includes('zh.mono'))
  jobs.value = j.jobs
}
const translatedOptions = () => outputs.value.map(f => f.rel)

async function run(fn, ...args) {
  error.value = ''
  dryRunResult.value = null
  try {
    const job = await fn(...args)
    if (job.cmd?.includes('--dry-run')) {
      await new Promise(r => setTimeout(r, 1500))
      const j = (await api.jobs()).jobs.find(x => x.id === job.id)
      if (j.state === 'done') {
        const log = await api.logs(j.log.split('/').pop(), 100)
        dryRunResult.value = log.content
        return
      }
    }
    load()
  } catch (e) { error.value = e.message }
}

onMounted(load)
timer = setInterval(load, 5000)
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div class="max-w-3xl mx-auto px-8 py-10">
    <h2 class="text-2xl font-bold mb-1">工具箱</h2>
    <p class="text-sm text-zinc-500 mb-8">后处理脚本：不影响译文缓存，只做重排版 / 目录 / 书签</p>

    <div v-if="error" class="mb-6 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">{{ error }}</div>

    <!-- build_final -->
    <section class="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-5 mb-5">
      <h3 class="font-semibold mb-1">重排版构建 <span class="text-xs text-zinc-500 font-normal">build_final.sh</span></h3>
      <p class="text-xs text-zinc-500 mb-4">译文已缓存时仅重排版（几分钟），不改译文内容。最终交付推荐入口。</p>
      <div class="grid grid-cols-3 gap-3 mb-3">
        <select v-model="bfBook" class="px-3 py-2 rounded-lg bg-zinc-900 border border-zinc-700 text-sm focus:border-teal-600 focus:outline-none">
          <option value="" disabled>选择源书</option>
          <option v-for="b in books" :key="b.name" :value="b.name">{{ b.name }}</option>
        </select>
        <select v-model="bfFont" class="px-3 py-2 rounded-lg bg-zinc-900 border border-zinc-700 text-sm focus:border-teal-600 focus:outline-none">
          <option value="serif">宋体（书籍风）</option>
          <option value="sans">黑体（屏显）</option>
        </select>
        <label class="flex items-center gap-2 px-3 py-2 rounded-lg border border-zinc-700 text-sm cursor-pointer">
          <input v-model="bfDryRun" type="checkbox" class="accent-teal-600" />只预览命令
        </label>
      </div>
      <div class="flex gap-4 mb-4 text-sm">
        <label class="flex items-center gap-2 cursor-pointer"><input v-model="bfNoWatermark" type="checkbox" class="accent-teal-600" />去水印</label>
        <label class="flex items-center gap-2 cursor-pointer"><input v-model="bfKeepLayer" type="checkbox" class="accent-teal-600" />保留原文层<span class="text-red-400/80">（体积×12）</span></label>
      </div>
      <button @click="run(api.buildFinal, { book: bfBook, font: bfFont, no_watermark: bfNoWatermark, keep_original_layer: bfKeepLayer, dry_run: bfDryRun })"
        :disabled="!bfBook"
        class="px-4 py-2 rounded-lg bg-teal-600 hover:bg-teal-500 disabled:opacity-50 text-sm font-medium transition-colors">运行</button>
      <pre v-if="dryRunResult" class="mt-4 px-4 py-3 rounded-lg bg-zinc-950 border border-zinc-800 text-xs text-zinc-300 font-mono whitespace-pre-wrap">{{ dryRunResult }}</pre>
    </section>

    <!-- rewrite_toc -->
    <section class="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-5 mb-5">
      <h3 class="font-semibold mb-1">目录 / 索引中文化 <span class="text-xs text-zinc-500 font-normal">rewrite_toc_index.py</span></h3>
      <p class="text-xs text-zinc-500 mb-4">对译文 PDF 原位重写目录/索引区域。页码留空则自动探测。</p>
      <div class="grid grid-cols-2 gap-3 mb-3">
        <select v-model="rtBook" class="px-3 py-2 rounded-lg bg-zinc-900 border border-zinc-700 text-sm focus:border-teal-600 focus:outline-none">
          <option value="" disabled>选择源书</option>
          <option v-for="b in books" :key="b.name" :value="b.name">{{ b.name }}</option>
        </select>
        <select v-model="rtTranslated" class="px-3 py-2 rounded-lg bg-zinc-900 border border-zinc-700 text-sm focus:border-teal-600 focus:outline-none">
          <option value="" disabled>选择译文 PDF</option>
          <option v-for="n in translatedOptions()" :key="n" :value="n">{{ n }}</option>
        </select>
        <input v-model="rtToc" placeholder="目录页范围，如 7-18（留空自动探测）"
          class="px-3 py-2 rounded-lg bg-zinc-900 border border-zinc-700 text-sm focus:border-teal-600 focus:outline-none" />
        <input v-model="rtIndex" placeholder="索引页范围，如 717-750（可空）"
          class="px-3 py-2 rounded-lg bg-zinc-900 border border-zinc-700 text-sm focus:border-teal-600 focus:outline-none" />
      </div>
      <button @click="run(api.rewriteToc, { book: rtBook, translated: rtTranslated, toc: rtToc, index: rtIndex })"
        :disabled="!rtBook || !rtTranslated"
        class="px-4 py-2 rounded-lg bg-teal-600 hover:bg-teal-500 disabled:opacity-50 text-sm font-medium transition-colors">运行</button>
    </section>

    <!-- bookmarks -->
    <section class="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-5">
      <h3 class="font-semibold mb-1">添加中文书签 <span class="text-xs text-zinc-500 font-normal">add_bookmarks.py</span></h3>
      <p class="text-xs text-zinc-500 mb-4">BabelDOC 产物通常已带中文书签，不确定时先跳过此步。</p>
      <div class="grid grid-cols-2 gap-3 mb-3">
        <select v-model="bmBook" class="px-3 py-2 rounded-lg bg-zinc-900 border border-zinc-700 text-sm focus:border-teal-600 focus:outline-none">
          <option value="" disabled>选择源书</option>
          <option v-for="b in books" :key="b.name" :value="b.name">{{ b.name }}</option>
        </select>
        <select v-model="bmTranslated" class="px-3 py-2 rounded-lg bg-zinc-900 border border-zinc-700 text-sm focus:border-teal-600 focus:outline-none">
          <option value="" disabled>选择译文 PDF</option>
          <option v-for="n in translatedOptions()" :key="n" :value="n">{{ n }}</option>
        </select>
      </div>
      <button @click="run(api.addBookmarks, { book: bmBook, translated: bmTranslated })"
        :disabled="!bmBook || !bmTranslated"
        class="px-4 py-2 rounded-lg bg-teal-600 hover:bg-teal-500 disabled:opacity-50 text-sm font-medium transition-colors">运行</button>
    </section>

    <!-- 任务历史 -->
    <section v-if="jobs.length" class="mt-8">
      <h3 class="font-semibold mb-3 text-sm text-zinc-400">最近任务（含后处理/术语表）</h3>
      <div class="space-y-2">
        <div v-for="j in jobs.slice(0, 8)" :key="j.id"
          class="flex items-center gap-3 px-4 py-2.5 rounded-lg border border-zinc-800 text-sm">
          <PhaseBadge :phase="j.state" />
          <span class="truncate flex-1 font-mono text-xs text-zinc-400">{{ j.cmd.join(' ') }}</span>
          <span class="text-xs text-zinc-600 shrink-0">{{ new Date(j.started * 1000).toLocaleString('zh-CN', { hour12: false }) }}</span>
        </div>
      </div>
    </section>
  </div>
</template>
