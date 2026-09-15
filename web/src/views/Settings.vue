<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'

const env = ref(null)
const keys = ref([])
const keyInput = ref('')
const keyName = ref('')
const busy = ref(false)
const message = ref('')

async function load() {
  env.value = await api.env()
  keys.value = (await api.keys()).keys
}

async function addKey() {
  const key = keyInput.value.trim()
  const name = keyName.value.trim()
  if (!key || busy.value) return
  busy.value = true
  message.value = ''
  try {
    await api.addKey(name, key)
    keyInput.value = ''
    keyName.value = ''
    message.value = '✓ 已保存到 .env'
    await load()
  } catch (e) {
    message.value = e.message
  }
  busy.value = false
}

async function removeKey(k) {
  if (!confirm(`删除「${k.name}」（${k.masked}）？`)) return
  message.value = ''
  try {
    await api.deleteKey(k.id)
    message.value = '✓ 已删除'
    await load()
  } catch (e) {
    message.value = e.message
  }
}

onMounted(load)
</script>

<template>
  <div class="max-w-2xl mx-auto px-8 py-10">
    <h2 class="text-2xl font-bold mb-1">设置</h2>
    <p class="text-sm text-zinc-500 mb-8">API Key 管理（BYOK，key 只存本地 .env，界面上始终脱敏显示）</p>

    <div v-if="env" class="space-y-4">
      <!-- API keys -->
      <div class="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-5">
        <div class="flex items-center justify-between mb-1">
          <p class="font-medium">API Key</p>
          <p class="text-sm tabular-nums" :class="keys.length ? 'text-emerald-400' : 'text-red-400'">
            {{ keys.length }} 个
          </p>
        </div>
        <p class="text-xs text-zinc-500 mb-4">
          支持自定义名称（如 main、spare1），仅限字母/数字/下划线。
          越多并行吞吐越高（约 1.5×/key），建议翻译任务的 workers 数 = key 数。
          需要开通 API 服务？
          <a href="https://github.com/snsnnd/Translator#云端版--会员服务" target="_blank" class="text-teal-400 hover:underline">联系我们（QQ 见主页）</a>
          ·
          <a href="https://github.com/snsnnd/Translator/blob/main/docs/BYOK.md" target="_blank" class="text-teal-400 hover:underline">机制说明</a>
        </p>

        <div class="space-y-2 mb-3">
          <div v-for="k in keys" :key="k.id"
            class="flex items-center gap-3 px-3 py-2 rounded-lg bg-zinc-950 border border-zinc-800">
            <span class="text-xs font-mono w-40 shrink-0 truncate" :title="k.id"
              :class="k.id.startsWith('API_KEY_') ? 'text-teal-500' : 'text-zinc-600'">{{ k.name }}</span>
            <span class="font-mono text-sm text-zinc-300 flex-1">{{ k.masked }}</span>
            <button @click="removeKey(k)"
              class="w-6 h-6 rounded flex items-center justify-center text-zinc-600 hover:text-red-400 text-xs shrink-0">🗑</button>
          </div>
          <p v-if="!keys.length" class="text-sm text-zinc-500 py-3 text-center border border-dashed border-zinc-800 rounded-lg">
            未配置 key，翻译无法启动
          </p>
        </div>

        <div class="flex gap-2 mb-2">
          <input v-model="keyName" @keyup.enter="addKey" placeholder="名称（如 main）"
            class="w-40 px-3 py-2 rounded-lg bg-zinc-900 border border-zinc-700 text-sm font-mono focus:border-teal-600 focus:outline-none" />
          <input v-model="keyInput" @keyup.enter="addKey" placeholder="key（id.secret），回车添加"
            class="flex-1 px-3 py-2 rounded-lg bg-zinc-900 border border-zinc-700 text-sm font-mono focus:border-teal-600 focus:outline-none" />
          <button @click="addKey" :disabled="!keyInput.trim() || !keyName.trim() || busy"
            class="px-4 py-2 rounded-lg bg-teal-600 hover:bg-teal-500 disabled:opacity-50 text-sm font-medium">添加</button>
        </div>
        <p v-if="message" class="text-xs mt-3" :class="message.startsWith('✓') ? 'text-emerald-400' : 'text-red-400'">{{ message }}</p>
      </div>

      <div class="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-5">
        <p class="font-medium">默认排除页 (EXCLUDE_PAGES)</p>
        <p class="text-xs text-zinc-500 mt-0.5">translate.sh 自动页探测时生效；并行任务在启动表单里单独填</p>
        <p class="mt-2 px-3 py-2 rounded-lg bg-zinc-950 border border-zinc-800 text-sm font-mono">
          {{ env.exclude_pages || '（未设置）' }}
        </p>
      </div>

      <div class="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-5">
        <p class="font-medium">翻译缓存</p>
        <p class="text-xs text-zinc-500 mt-0.5">~/.cache/babeldoc/cache.v1.db — 相同段落+相同提示词不重复计费；提示词/术语表变更会触发真实重译。清缓存 = 删除该文件。</p>
      </div>
    </div>
  </div>
</template>
