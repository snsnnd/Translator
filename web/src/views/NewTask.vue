<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import PhaseBadge from '../components/PhaseBadge.vue'

const route = useRoute()
const router = useRouter()

const books = ref([])
const book = ref(route.query.book || '')
const workers = ref(3)
const fromPage = ref(null)
const toPage = ref(null)
const exclude = ref('')
const qps = ref(16)
const serif = ref(false)
const noWatermark = ref(true)
const skipClean = ref(false)
const makeGlossary = ref(true)
const pageInfo = ref(null)
const starting = ref(false)
const error = ref('')

// 术语表
const showGlossary = ref(false)
const glossary = ref('')
const glossaryDirty = ref(false)
const glossaryJob = ref(null)
let glossaryTimer = null

const selectedBook = computed(() => books.value.find(b => b.name === book.value))

async function loadBooks() {
  const data = await api.books()
  books.value = data.books
  if (!book.value && data.books.length) book.value = data.books[0].name
  if (book.value) fetchPages()
}

async function fetchPages() {
  pageInfo.value = null
  if (!book.value) return
  try { pageInfo.value = await api.pages(book.value) } catch {}
}

async function openGlossary() {
  showGlossary.value = true
  const g = await api.glossary()
  glossary.value = g.content
  glossaryDirty.value = false
}

async function saveGlossary() {
  await api.saveGlossary(glossary.value)
  glossaryDirty.value = false
}

async function genGlossary() {
  error.value = ''
  try {
    const job = await api.genGlossary(book.value, '')
    glossaryJob.value = job
    glossaryTimer = setInterval(async () => {
      const jobs = await api.jobs()
      glossaryJob.value = jobs.jobs.find(x => x.id === job.id)
      if (glossaryJob.value.state === 'done') {
        clearInterval(glossaryTimer)
        const g = await api.glossary()
        glossary.value = g.content
        makeGlossary.value = false
      }
    }, 3000)
  } catch (e) { error.value = e.message }
}

async function start() {
  error.value = ''
  if (!book.value) { error.value = '请选择一本书'; return }
  starting.value = true
  try {
    await api.startTask({
      book: book.value, workers: workers.value,
      from_page: fromPage.value || null, to_page: toPage.value || null,
      exclude: exclude.value, qps: qps.value,
      serif: serif.value, no_watermark: noWatermark.value,
      skip_clean: skipClean.value, make_glossary: makeGlossary.value,
    })
    router.push({ name: 'progress' })
  } catch (e) {
    error.value = e.message
  }
  starting.value = false
}

onMounted(loadBooks)
</script>

<template>
  <div class="max-w-3xl mx-auto px-8 py-10">
    <h2 class="text-2xl font-bold mb-8">新建翻译任务</h2>

    <div v-if="error" class="mb-6 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">{{ error }}</div>

    <div class="space-y-6">
      <!-- 选书 -->
      <div>
        <label class="block text-sm font-medium text-zinc-300 mb-2">选择书籍</label>
        <select v-model="book" @change="fetchPages"
          class="w-full px-3 py-2.5 rounded-lg bg-zinc-900 border border-zinc-700 text-sm focus:border-teal-600 focus:outline-none">
          <option v-for="b in books" :key="b.name" :value="b.name">{{ b.name }}</option>
        </select>
        <p v-if="pageInfo" class="text-xs text-zinc-500 mt-1.5">
          共 {{ pageInfo.total }} 页，有效页（有文字层）{{ pageInfo.valid }} 页
        </p>
      </div>

      <!-- 并行参数 -->
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium text-zinc-300 mb-2">并行进程数 (workers)</label>
          <input v-model.number="workers" type="number" min="1" max="16"
            class="w-full px-3 py-2.5 rounded-lg bg-zinc-900 border border-zinc-700 text-sm focus:border-teal-600 focus:outline-none" />
          <p class="text-xs text-zinc-500 mt-1.5">≤ .env 里的 API key 数量，每进程 16 QPS</p>
        </div>
        <div>
          <label class="block text-sm font-medium text-zinc-300 mb-2">每进程 QPS</label>
          <input v-model.number="qps" type="number" min="1" max="32"
            class="w-full px-3 py-2.5 rounded-lg bg-zinc-900 border border-zinc-700 text-sm focus:border-teal-600 focus:outline-none" />
        </div>
      </div>

      <!-- 页码范围 -->
      <div class="grid grid-cols-3 gap-4">
        <div>
          <label class="block text-sm font-medium text-zinc-300 mb-2">起始页</label>
          <input v-model.number="fromPage" type="number" min="1" placeholder="1"
            class="w-full px-3 py-2.5 rounded-lg bg-zinc-900 border border-zinc-700 text-sm focus:border-teal-600 focus:outline-none" />
        </div>
        <div>
          <label class="block text-sm font-medium text-zinc-300 mb-2">结束页</label>
          <input v-model.number="toPage" type="number" min="1" :placeholder="pageInfo ? String(pageInfo.total) : '末页'"
            class="w-full px-3 py-2.5 rounded-lg bg-zinc-900 border border-zinc-700 text-sm focus:border-teal-600 focus:outline-none" />
        </div>
        <div>
          <label class="block text-sm font-medium text-zinc-300 mb-2">排除页</label>
          <input v-model="exclude" placeholder="如 7-12（目录页）"
            class="w-full px-3 py-2.5 rounded-lg bg-zinc-900 border border-zinc-700 text-sm focus:border-teal-600 focus:outline-none" />
          <p class="text-xs text-zinc-500 mt-1.5">目录页建议不翻，保留英文最稳</p>
        </div>
      </div>

      <!-- 排版选项 -->
      <div>
        <label class="block text-sm font-medium text-zinc-300 mb-3">排版选项</label>
        <div class="space-y-2.5">
          <label class="flex items-start gap-3 cursor-pointer">
            <input v-model="serif" type="checkbox" class="mt-0.5 accent-teal-600" />
            <span class="text-sm">宋体排版（serif，书籍风格）<span class="text-zinc-500">不勾则用黑体（屏显）</span></span>
          </label>
          <label class="flex items-start gap-3 cursor-pointer">
            <input v-model="noWatermark" type="checkbox" class="mt-0.5 accent-teal-600" />
            <span class="text-sm">去除水印署名 <span class="text-zinc-500">产物文件名会带 .no_watermark 中缀</span></span>
          </label>
          <label class="flex items-start gap-3 cursor-pointer">
            <input v-model="skipClean" type="checkbox" class="mt-0.5 accent-teal-600" />
            <span class="text-sm">保留英文原文层（可搜索/复制）<span class="text-red-400/80">体积约 ×12，慎选</span></span>
          </label>
        </div>
      </div>

      <!-- 术语表 -->
      <div class="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm font-medium">术语表 <span class="text-zinc-500 font-normal">prompts/book_prompt.txt</span></p>
            <p class="text-xs text-zinc-500 mt-0.5">按书覆盖。换书必须重新生成，生成后翻译会走新缓存键</p>
          </div>
          <div class="flex gap-2 shrink-0">
            <button @click="openGlossary" class="px-3 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-500 text-xs transition-colors">查看 / 编辑</button>
            <button @click="genGlossary" :disabled="!book || glossaryJob && ['queued','running'].includes(glossaryJob.state)"
              class="px-3 py-1.5 rounded-lg border border-teal-700 text-teal-400 hover:bg-teal-600/10 text-xs transition-colors disabled:opacity-50">
              {{ glossaryJob?.state === 'running' ? '生成中…' : '自动生成' }}
            </button>
          </div>
        </div>
        <div v-if="glossaryJob && !['done'].includes(glossaryJob.state)" class="flex items-center gap-2 mt-3">
          <PhaseBadge :phase="glossaryJob.state" />
          <span v-if="glossaryJob.state === 'failed'" class="text-xs text-red-400">生成失败，查看 任务进度 → 日志</span>
        </div>
        <label class="flex items-center gap-3 cursor-pointer mt-3">
          <input v-model="makeGlossary" type="checkbox" class="accent-teal-600" />
          <span class="text-sm">翻译前自动重新生成术语表</span>
        </label>
      </div>

      <!-- 提交 -->
      <div class="flex items-center gap-4 pt-2">
        <button @click="start" :disabled="starting || !book"
          class="px-6 py-3 rounded-xl bg-teal-600 hover:bg-teal-500 disabled:opacity-50 font-medium transition-colors">
          {{ starting ? '启动中…' : '开始翻译' }}
        </button>
        <p v-if="makeGlossary" class="text-xs text-zinc-500">将先自动生成术语表（1~3 分钟），随后启动翻译</p>
      </div>
    </div>

    <!-- 术语表编辑弹层 -->
    <div v-if="showGlossary" class="fixed inset-0 bg-black/60 flex items-center justify-center p-8 z-50" @click.self="showGlossary = false">
      <div class="w-full max-w-2xl bg-zinc-900 rounded-2xl border border-zinc-700 p-6">
        <div class="flex items-center justify-between mb-4">
          <h3 class="font-semibold">术语表（system prompt）</h3>
          <button @click="showGlossary = false" class="text-zinc-500 hover:text-zinc-300">✕</button>
        </div>
        <textarea v-model="glossary" @input="glossaryDirty = true" rows="16" spellcheck="false"
          class="w-full px-3 py-2 rounded-lg bg-zinc-950 border border-zinc-700 text-xs font-mono focus:border-teal-600 focus:outline-none resize-y"></textarea>
        <div class="flex justify-end gap-2 mt-4">
          <button @click="showGlossary = false" class="px-4 py-2 rounded-lg border border-zinc-700 text-sm">取消</button>
          <button @click="saveGlossary" :disabled="!glossaryDirty"
            class="px-4 py-2 rounded-lg bg-teal-600 hover:bg-teal-500 disabled:opacity-50 text-sm font-medium">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>
