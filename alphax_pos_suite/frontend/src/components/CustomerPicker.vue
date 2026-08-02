<script setup>
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import { usePOSStore } from '../stores/pos'
import AppModal from './AppModal.vue'

const { t } = useI18n()
const store = usePOSStore()
const emit = defineEmits(['close'])

const query = ref('')
const results = ref([])
const loading = ref(false)

let timer = null
watch(query, (q) => {
  clearTimeout(timer)
  timer = setTimeout(async () => {
    loading.value = true
    try { results.value = await api.searchCustomers(q) || [] }
    catch { results.value = [] }
    loading.value = false
  }, 200)
}, { immediate: true })

function pick(name) {
  store.setCustomer(name)
  emit('close')
}
</script>

<template>
  <AppModal :title="t('cart.pick_customer')" size="md" @close="emit('close')">
    <input
      class="input"
      v-model="query"
      :placeholder="t('app.search')"
      autofocus
    />
    <div class="result-list">
      <div v-if="loading" class="muted">…</div>
      <button
        v-for="c in results"
        :key="c.name"
        class="result"
        @click="pick(c.name)"
      >
        <div class="result-main">{{ c.customer_name || c.name }}</div>
        <div class="result-sub" v-if="c.mobile_no">{{ c.mobile_no }}</div>
      </button>
      <div v-if="!loading && results.length === 0 && query" class="muted">∅</div>
    </div>
  </AppModal>
</template>

<style scoped>
.result-list { display: flex; flex-direction: column; gap: 4px; margin-block-start: 12px; max-height: 50vh; overflow-y: auto; }
.result {
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  padding: 10px 12px;
  text-align: start;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.result:hover { background: var(--surface-2); border-color: var(--accent); }
.result-main { font-size: 13px; font-weight: 500; }
.result-sub { font-size: 11px; color: var(--text-muted); }
.muted { color: var(--text-dim); padding: 16px; text-align: center; font-size: 13px; }
</style>
