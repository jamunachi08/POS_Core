<script setup>
import { ref } from 'vue'

const toasts = ref([])

function show(msg, kind = 'info', ttl = 3000) {
  const id = Math.random().toString(36).slice(2)
  toasts.value.push({ id, msg, kind })
  setTimeout(() => {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }, ttl)
}

defineExpose({ show })
</script>

<template>
  <div class="toast-wrap">
    <transition-group name="toast">
      <div v-for="t in toasts" :key="t.id" class="toast" :class="`toast-${t.kind}`">
        {{ t.msg }}
      </div>
    </transition-group>
  </div>
</template>

<style scoped>
.toast-wrap {
  position: fixed;
  inset-block-end: 24px;
  inset-inline-start: 50%;
  transform: translateX(-50%);
  z-index: 10000;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  pointer-events: none;
}
[dir="rtl"] .toast-wrap { transform: translateX(50%); }
.toast {
  padding: 11px 18px;
  background: var(--text);
  color: var(--surface);
  border-radius: var(--r-md);
  font-size: 13px;
  font-weight: 500;
  box-shadow: var(--shadow-md);
  pointer-events: auto;
}
.toast-success { background: var(--accent); }
.toast-error { background: var(--danger); }
.toast-warn { background: var(--warn); }
.toast-enter-active, .toast-leave-active { transition: opacity 0.2s, transform 0.2s; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(8px); }
</style>
