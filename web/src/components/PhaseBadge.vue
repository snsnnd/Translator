<script setup>
defineProps({
  phase: String,
})
const map = {
  parsing: ['版面解析中', 'bg-amber-500/15 text-amber-400'],
  running: ['翻译中', 'bg-teal-500/15 text-teal-400'],
  merging: ['合并中', 'bg-blue-500/15 text-blue-400'],
  done: ['已完成', 'bg-emerald-500/15 text-emerald-400'],
  failed: ['失败', 'bg-red-500/15 text-red-400'],
  detached: ['后台运行中', 'bg-violet-500/15 text-violet-400'],
  queued: ['排队中', 'bg-zinc-500/15 text-zinc-400'],
  cancelled: ['已取消', 'bg-zinc-500/15 text-zinc-400'],
}
</script>

<template>
  <span v-if="phase" class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
    :class="(map[phase] || [phase, 'bg-zinc-500/15 text-zinc-400'])[1]">
    <span v-if="phase === 'running' || phase === 'parsing' || phase === 'merging'"
      class="w-1.5 h-1.5 rounded-full bg-current animate-pulse mr-1.5"></span>
    {{ (map[phase] || [phase])[0] }}
  </span>
</template>
