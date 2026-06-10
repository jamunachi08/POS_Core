<script setup>
defineProps({
  title: String,
  size: { type: String, default: 'md' }
})
defineEmits(['close'])
</script>

<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <div class="modal" :class="`modal-${size}`">
      <header class="modal-head" v-if="title || $slots.header">
        <slot name="header">
          <h3 class="modal-title">{{ title }}</h3>
        </slot>
        <button class="modal-close" @click="$emit('close')" :aria-label="$t('app.close')">×</button>
      </header>
      <div class="modal-body">
        <slot />
      </div>
      <footer class="modal-foot" v-if="$slots.footer">
        <slot name="footer" />
      </footer>
    </div>
  </div>
</template>

<style scoped>
.modal-backdrop {
  position: fixed; inset: 0;
  background: rgba(20, 20, 20, 0.55);
  display: grid; place-items: center;
  z-index: 9000;
  padding: 20px;
  animation: fade 0.16s ease-out;
}
@keyframes fade { from { opacity: 0; } to { opacity: 1; } }

.modal {
  background: var(--surface);
  border-radius: var(--r-lg);
  width: 100%;
  max-width: 480px;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-overlay);
  animation: pop 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
}
@keyframes pop { from { transform: scale(0.96); opacity: 0; } to { transform: scale(1); opacity: 1; } }
.modal-sm { max-width: 380px; }
.modal-lg { max-width: 640px; }
.modal-xl { max-width: 820px; }

.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-block-end: 1px solid var(--border);
}
.modal-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
}
.modal-close {
  background: transparent;
  border: none;
  width: 32px; height: 32px;
  border-radius: 50%;
  color: var(--text-muted);
  font-size: 22px;
  line-height: 1;
  display: grid; place-items: center;
}
.modal-close:hover { background: var(--surface-2); color: var(--text); }

.modal-body { padding: 20px; overflow-y: auto; flex: 1; }
.modal-foot {
  padding: 14px 20px;
  border-block-start: 1px solid var(--border);
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>
