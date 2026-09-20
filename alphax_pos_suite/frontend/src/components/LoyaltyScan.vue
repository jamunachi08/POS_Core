<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import AppModal from './AppModal.vue'

const { t } = useI18n()
const store = usePOSStore()
const emit = defineEmits(['close'])

const card = ref('')
const error = ref('')
const inputRef = ref(null)

onMounted(() => inputRef.value?.focus())

async function lookup() {
  if (!card.value.trim()) return
  error.value = ''
  const w = await store.lookupLoyaltyCard(card.value.trim())
  if (!w) {
    error.value = t('errors.permission_denied')
    return
  }
  emit('close')
}
</script>

<template>
  <AppModal :title="t('cart.scan_loyalty')" size="sm" @close="emit('close')">
    <label class="label">{{ t('cart.loyalty_card') }}</label>
    <input
      ref="inputRef"
      class="input"
      v-model="card"
      autocomplete="off"
      @keydown.enter="lookup"
      :placeholder="t('cart.loyalty_card')"
    />
    <div v-if="error" class="error">{{ error }}</div>

    <template #footer>
      <button class="btn" @click="emit('close')">{{ t('app.cancel') }}</button>
      <button class="btn btn-primary" @click="lookup" :disabled="!card.trim()">
        {{ t('cart.look_up') }}
      </button>
    </template>
  </AppModal>
</template>

<style scoped>
.error {
  margin-block-start: 10px;
  padding: 10px 12px;
  background: var(--danger-soft);
  color: var(--danger);
  border-radius: var(--r-md);
  font-size: 13px;
}
</style>
