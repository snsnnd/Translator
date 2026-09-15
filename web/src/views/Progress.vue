<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { api } from '../api'
import PhaseBadge from '../components/PhaseBadge.vue'

const status = ref(null)
const statusMtime = ref(null)
const logsList = ref([])
const activeLog = ref('orchestrator.log')
const logContent = ref('')
const cancelling = ref(false)
const error = ref('')
const follow = ref(true)
const logBox = ref(null)
let timer = null
let logTimer = null

const total = computed(() => status.value?.total)
const workers = computed(() => status.value?.workers || [])
// running/merging = 正在跑; detached = 后台仍在跑; done/failed = 只是历史记录
const isActive = computed(() => ['running', 'merging', 'detached'].includes(status.value?.phase))
const isRunning = computed(() => ['running', 'merging'].includes(status.value?.phase))

function fmtEta(sec) {
  if (sec == null || sec <= 0) return '—'
  const m = Math.round(sec / 60)
  return m >= 60 ? `${Math.floor(m / 60)} 时 ${m % 60} 分` : `${m} 分`
}
function fmtTime(iso) {
  return iso ? new Date(iso).toLocaleTimeString('zh-CN', { hour12: false }) : '—'
}

const workerStateClass = {
  parsing: 'border-amber-600/40 bg-amber-500/5',
  running: 'border-teal-600/40 bg-teal-500/5',
  done: 'border-emerald-700/40 bg-emerald-500/5',
  failed: 'border-red-700/40 bg-red-500/5',
}

async function poll() {
  try {
    const data = await api.taskStatus()
    status.value = data.status
    statusMtime.value = data.mtime
  } catch (e) { error.value = e.message }
}

async function pollLog() {
  try {
    const data = await api.logs(activeLog.value, 400)
    logContent.value = data.content
    if (follow.value && logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight
  } catch {}
}

async function cancel() {
  if (!confirm('确定取消当前翻译任务？已完成的分片会保留，重跑同一命令可断点续传。')) return
  cancelling.value = true
  try { await api.cancelTask() } catch (e) { error.value = e.message }
  cancelling.value = false
  poll()
}

async function clearRecord() {
  try {
    await api.clearTask()
    status.value = null
  } catch (e) { error.value = e.message }
}

watch(activeLog, pollLog)

onMounted(async () => {
  poll()
  const logs = await api.logsList()
  logsList.value = logs.logs.filter(n => n !== 'status.json')
  if (!logsList.value.includes('orchestrator.log') && logsList.value.length) activeLog.value = logsList.value[0]
  pollLog()
  timer = setInterval(poll, 3000)
  logTimer = setInterval(pollLog, 4000)
})
onUnmounted(() => { clearInterval(timer); clearInterval(logTimer) })
</script>

<template>
  <div class="max-w-5xl mx-auto px-8 py-10">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h2 class="text-2xl font-bold">任务进度</h2>
        <p class="text-sm text-zinc-500 mt-1 truncate max-w-xl">{{ status?.book || '暂无任务' }}</p>
      </div>
      <div class="flex items-center gap-3 shrink-0">
        <PhaseBadge v-if="status" :phase="status.phase" />
        <button v-if="isRunning" @click="cancel" :disabled="cancelling"
          class="px-4 py-2 rounded-lg border border-red-800 text-red-400 hover:bg-red-500/10 text-sm transition-colors disabled:opacity-50">
          {{ cancelling ? '取消中…' : '取消任务' }}
        </button>
        <button v-if="status && !isActive" @click="clearRecord"
          class="px-4 py-2 rounded-lg border border-zinc-700 text-zinc-400 hover:border-zinc-500 text-sm transition-colors">
          清除记录
        </button>
      </div>
    </div>

    <div v-if="status && !isActive"
      class="mb-6 px-4 py-3 rounded-lg bg-zinc-800/40 border border-zinc-700 text-sm text-zinc-400">
      当前没有正在运行的任务。下面是 <b class="text-zinc-300">上次任务</b> 的记录，产物可在 <RouterLink to="/output" class="text-teal-400 hover:underline">产物页</RouterLink> 查看。
    </div>

    <div v-if="!status" class="text-center py-24 text-zinc-500">
      还没有任务记录。去 <RouterLink to="/new" class="text-teal-400 hover:underline">新建翻译任务</RouterLink>
    </div>

    <template v-else>
      <!-- 总进度 -->
      <div class="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 mb-6">
        <p v-if="!isActive" class="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-3">上次任务</p>
        <div class="flex items-end justify-between mb-3">
          <div class="flex items-baseline gap-2">
            <span class="text-4xl font-bold tabular-nums">{{ total?.percent?.toFixed(1) ?? '—' }}</span>
            <span class="text-lg text-zinc-500">%</span>
          </div>
          <div class="text-right text-sm text-zinc-400 space-y-0.5">
            <p>{{ total?.done ?? 0 }} / {{ total?.pages ?? 0 }} 页</p>
            <p v-if="total?.speed_pages_per_min">速度 {{ total.speed_pages_per_min.toFixed(1) }} 页/分</p>
            <p v-if="isRunning">剩余约 {{ fmtEta(total?.eta_seconds) }}</p>
          </div>
        </div>
        <div class="h-3 rounded-full bg-zinc-800 overflow-hidden">
          <div class="h-full rounded-full transition-all duration-700"
            :class="status.phase === 'failed' ? 'bg-red-500' : 'bg-teal-500'"
            :style="{ width: (total?.percent || 0) + '%' }"></div>
        </div>
        <div class="flex justify-between text-xs text-zinc-600 mt-3">
          <span>开始 {{ fmtTime(status.started_at) }}</span>
          <span>更新 {{ fmtTime(status.updated_at) }}</span>
        </div>
        <div v-if="status.phase === 'done' && status.output"
          class="mt-4 px-4 py-3 rounded-lg bg-emerald-500/10 border border-emerald-600/30 text-sm text-emerald-400">
          ✓ 翻译完成：<RouterLink to="/output" class="underline">去产物页查看 / 预览 / 下载</RouterLink>
        </div>
        <div v-if="status.phase === 'failed'" class="mt-4 px-4 py-3 rounded-lg bg-red-500/10 border border-red-600/30 text-sm text-red-400">
          任务失败。查看下方日志定位原因；修复后用原参数重跑即可断点续传（已完成的分片不重复计费）。
        </div>
        <div v-if="status.phase === 'detached'" class="mt-4 px-4 py-3 rounded-lg bg-violet-500/10 border border-violet-600/30 text-sm text-violet-300">
          编排器在后台独立运行（CLI 启动或监控退出），进度每 30s 刷新一次。
        </div>
      </div>

      <!-- Worker 矩阵 -->
      <div v-if="workers.length" class="grid grid-cols-2 md:grid-cols-3 gap-3 mb-6">
        <div v-for="w in workers" :key="w.id"
          class="rounded-xl border p-4" :class="workerStateClass[w.state] || 'border-zinc-800'">
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm font-semibold">Worker {{ w.id }}</span>
            <PhaseBadge :phase="w.state" />
          </div>
          <template v-if="w.pages_total">
            <div class="h-1.5 rounded-full bg-zinc-800 overflow-hidden mb-2">
              <div class="h-full bg-teal-500 transition-all duration-700"
                :style="{ width: ((w.pages_done || 0) / w.pages_total * 100) + '%' }"></div>
            </div>
            <p class="text-xs text-zinc-400 tabular-nums">
              {{ w.pages_done || 0 }} / {{ w.pages_total }} 页
              <template v-if="w.eta_sec != null && w.state === 'running'"> · 剩 {{ fmtEta(w.eta_sec) }}</template>
            </p>
          </template>
          <p v-else class="text-xs text-zinc-500">版面解析中…（CPU 密集）</p>
        </div>
      </div>

      <!-- 日志 -->
      <div class="rounded-2xl border border-zinc-800 bg-zinc-900/40 overflow-hidden">
        <div class="flex items-center gap-2 px-4 py-2.5 border-b border-zinc-800 overflow-x-auto">
          <button v-for="n in logsList" :key="n" @click="activeLog = n"
            class="px-3 py-1 rounded-md text-xs whitespace-nowrap transition-colors"
            :class="activeLog === n ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'">
            {{ n }}
          </button>
          <label class="ml-auto flex items-center gap-1.5 text-xs text-zinc-500 cursor-pointer shrink-0">
            <input v-model="follow" type="checkbox" class="accent-teal-600" />自动滚动
          </label>
        </div>
        <pre ref="logBox" class="h-72 overflow-auto px-4 py-3 text-[11px] leading-relaxed text-zinc-400 font-mono whitespace-pre-wrap">{{ logContent || '（暂无日志）' }}</pre>
      </div>
    </template>
  </div>
</template>
