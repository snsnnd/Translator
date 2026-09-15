<script setup>
import { ref } from 'vue'

const STORAGE_KEY = 'translator_sponsor_next_show'
const DAY = 24 * 60 * 60 * 1000

// TODO: 替换为你的真实链接
const LINKS = {
  sponsor: 'https://github.com/snsnnd/Translator#赞助--sponsor',
  membership: 'https://github.com/snsnnd/Translator#云端版--会员服务',
}

const show = ref(localStorage.getItem(STORAGE_KEY) === null
  || Date.now() > Number(localStorage.getItem(STORAGE_KEY) || 0))

function dismiss(days = 7) {
  localStorage.setItem(STORAGE_KEY, String(Date.now() + days * DAY))
  show.value = false
}
</script>

<template>
  <div v-if="show" class="fixed inset-0 bg-black/60 flex items-center justify-center p-8 z-50" @click.self="dismiss(1)">
    <div class="w-full max-w-md bg-zinc-900 rounded-2xl border border-zinc-700 p-6 relative">
      <button @click="dismiss(1)" class="absolute top-4 right-4 text-zinc-500 hover:text-zinc-300">✕</button>

      <p class="text-xs font-medium text-teal-400 uppercase tracking-wider mb-2">支持这个项目</p>
      <h3 class="text-lg font-bold mb-2">喜欢这个工具？</h3>
      <p class="text-sm text-zinc-400 leading-relaxed mb-5">
        PDF 书籍翻译器完全开源免费（AGPL-3.0）。如果它帮你翻完了那本几百页的大部头，
        可以考虑请作者喝杯咖啡 ☕ —— 你的支持是继续维护更新的动力。
      </p>

      <div class="rounded-xl border border-teal-800/40 bg-teal-500/5 p-4 mb-5">
        <p class="text-sm font-medium text-teal-300 mb-1">不想折腾环境？</p>
        <p class="text-xs text-zinc-400 leading-relaxed">
          会员托管版：打开网页即用，翻译额度全包，无需自备 API key。
          <a :href="LINKS.membership" target="_blank" class="text-teal-400 hover:underline font-medium">了解详情 →</a>
        </p>
      </div>

      <div class="flex gap-2">
        <a :href="LINKS.sponsor" target="_blank"
          class="flex-1 px-4 py-2.5 rounded-lg bg-teal-600 hover:bg-teal-500 text-sm font-medium text-center transition-colors">
          去赞助
        </a>
        <button @click="dismiss(7)"
          class="flex-1 px-4 py-2.5 rounded-lg border border-zinc-700 hover:border-zinc-500 text-sm text-zinc-400 transition-colors">
          7 天内不再显示
        </button>
      </div>
      <button @click="dismiss(1)" class="w-full text-center text-xs text-zinc-600 hover:text-zinc-400 mt-3">
          今天先不看了
      </button>
    </div>
  </div>
</template>
