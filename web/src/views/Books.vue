<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'

const router = useRouter()
const books = ref([])
const loading = ref(true)
const error = ref('')
const uploading = ref(false)
const fileInput = ref(null)
const dragged = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.books()
    books.value = data.books
  } catch (e) {
    error.value = e.message
  }
  loading.value = false
}

async function upload(files) {
  uploading.value = true
  for (const f of files) {
    try { await api.upload(f) } catch (e) { error.value = e.message }
  }
  uploading.value = false
  load()
}

function fmtSize(n) {
  if (n > 1 << 30) return (n / (1 << 30)).toFixed(2) + ' GB'
  if (n > 1 << 20) return (n / (1 << 20)).toFixed(1) + ' MB'
  return (n / 1024).toFixed(0) + ' KB'
}

// 译文变体标签: 文件名里的中缀区分标准版/无水印版
function variantLabel(f) {
  if (f.name.includes('.no_watermark.')) return '译文（无水印）'
  if (f.name.includes('.zh.dual.')) return '译文（双语对照）'
  return '译文'
}
// rel 相对 output/(可能含书名文件夹), 逐段编码
const fileUrl = (rel) => '/output-files/' + rel.split('/').map(encodeURIComponent).join('/')

function toggleMenu(name) {
  openMenu.value = openMenu.value === name ? null : name
}
const openMenu = ref(null)
function closeMenu() { openMenu.value = null }

async function deleteBook(b) {
  const extra = b.translated?.length ? '\n（译文产物仍保留在产物页，不会一起删除）' : ''
  if (!confirm(`确定删除源书？\n${b.name}${extra}`)) return
  try {
    await api.deleteBook(b.name)
    closeMenu()
    load()
  } catch (e) { error.value = e.message }
}

onMounted(load)
</script>

<template>
  <div class="max-w-5xl mx-auto px-8 py-10">
    <div class="flex items-center justify-between mb-8">
      <div>
        <h2 class="text-2xl font-bold">书架</h2>
        <p class="text-sm text-zinc-500 mt-1">books/ 目录下的源 PDF</p>
      </div>
      <button @click="fileInput.click()" :disabled="uploading"
        class="px-4 py-2 rounded-lg bg-teal-600 hover:bg-teal-500 disabled:opacity-50 text-sm font-medium transition-colors">
        {{ uploading ? '上传中…' : '上传 PDF' }}
      </button>
      <input ref="fileInput" type="file" accept=".pdf" multiple class="hidden" @change="upload($event.target.files)" />
    </div>

    <div v-if="error" class="mb-6 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">{{ error }}</div>

    <div v-if="!loading && books.length === 0"
      class="border-2 border-dashed border-zinc-800 rounded-2xl py-24 text-center text-zinc-500"
      :class="{ 'border-teal-600/50': dragged }"
      @dragover.prevent="dragged = true" @dragleave="dragged = false" @drop.prevent="dragged = false; upload($event.dataTransfer.files)">
      把 PDF 拖到这里，或点击右上角上传
    </div>

    <div class="space-y-3" @click.capture="closeMenu">
      <div v-for="b in books" :key="b.name"
        class="group flex items-center gap-4 px-5 py-4 rounded-xl border border-zinc-800 bg-zinc-900/40 hover:border-zinc-700 transition-colors">
        <div class="w-10 h-12 shrink-0 rounded bg-zinc-800 flex items-center justify-center text-lg">📕</div>
        <div class="flex-1 min-w-0">
          <p class="font-medium truncate" :title="b.name">{{ b.name }}</p>
          <p class="text-xs text-zinc-500 mt-0.5">
            {{ fmtSize(b.size) }}<template v-if="b.pages"> · {{ b.pages }} 页</template>
            <template v-if="b.translated?.length"> · 已有译文</template>
          </p>
        </div>
        <span v-if="b.translated?.length"
          class="px-2.5 py-0.5 rounded-full text-xs bg-emerald-500/15 text-emerald-400 shrink-0">✓ 已翻译</span>

        <!-- 下载: 原文 / 各译文版本 -->
        <div v-if="b.translated?.length" class="relative shrink-0" @click.stop>
          <button @click="toggleMenu(b.name)"
            class="px-4 py-2 rounded-lg border border-zinc-700 hover:border-zinc-500 text-sm transition-colors">
            下载 ▾
          </button>
          <div v-if="openMenu === b.name"
            class="absolute right-0 top-full mt-1.5 w-64 rounded-xl border border-zinc-700 bg-zinc-900 shadow-xl py-1.5 z-20">
            <a :href="api.bookFile(b.name)" :download="b.name"
              class="flex items-center justify-between px-4 py-2 text-sm hover:bg-zinc-800">
              <span>原文 PDF</span><span class="text-xs text-zinc-500">{{ fmtSize(b.size) }}</span>
            </a>
            <div v-for="f in b.translated" :key="f.rel" class="border-t border-zinc-800 first:border-t-0">
              <a :href="fileUrl(f.rel)" :download="f.name"
                class="flex items-center justify-between px-4 py-2 text-sm hover:bg-zinc-800">
                <span>{{ variantLabel(f) }}</span><span class="text-xs text-zinc-500">{{ fmtSize(f.size) }}</span>
              </a>
            </div>
            <RouterLink :to="{ name: 'output' }"
              class="block px-4 py-2 text-xs text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 border-t border-zinc-800">
              预览 / 更多产物 → 产物页
            </RouterLink>
          </div>
        </div>

        <!-- 已翻译: 翻译按钮标黑, 保留重翻入口 -->
        <template v-if="b.translated?.length">
          <button disabled
            class="px-4 py-2 rounded-lg bg-zinc-800 text-zinc-600 text-sm font-medium cursor-not-allowed shrink-0"
            title="该书已有译文；如需重翻请点右侧「重翻」">
            开始翻译
          </button>
          <button @click="router.push({ name: 'new', query: { book: b.name } })"
            class="px-3 py-2 rounded-lg text-sm text-zinc-400 hover:text-teal-400 transition-colors shrink-0">
            重翻
          </button>
        </template>
        <button v-else @click="router.push({ name: 'new', query: { book: b.name } })"
          class="px-4 py-2 rounded-lg bg-teal-600/90 hover:bg-teal-500 text-sm font-medium transition-colors shrink-0">
          开始翻译
        </button>

        <button @click.stop="deleteBook(b)"
          class="w-8 h-8 rounded-lg flex items-center justify-center text-zinc-600 hover:text-red-400 hover:bg-red-500/10 transition-colors shrink-0"
          title="删除源书">
          🗑
        </button>
      </div>
    </div>
  </div>
</template>
