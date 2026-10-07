<script setup>
import { computed } from 'vue'
import { haptics } from '../composables/haptics'

const props = defineProps({
  modelValue: { type: String, default: '' },
  decimals:   { type: Boolean, default: true },
  // Add a "00" key — common on POS keypads
  doubleZero: { type: Boolean, default: true }
})
const emit = defineEmits(['update:modelValue', 'enter', 'clear'])

const keys = computed(() => {
  const k = ['1','2','3','4','5','6','7','8','9']
  k.push(props.doubleZero ? '00' : 'C')
  k.push('0')
  k.push(props.decimals ? '.' : '⌫')
  return k
})

function press(k) {
  haptics.tap()
  if (k === 'C') return emit('clear')
  if (k === '⌫') return emit('update:modelValue', String(props.modelValue).slice(0, -1))
  if (k === '.' && String(props.modelValue).includes('.')) return
  if (k === '.' && props.modelValue === '') return emit('update:modelValue', '0.')
  emit('update:modelValue', String(props.modelValue) + k)
}
</script>

<template>
  <div class="keypad">
    <button v-for="k in keys" :key="k" class="key" @click="press(k)">{{ k }}</button>
  </div>
</template>

<style scoped>
.keypad {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
}
.key {
  padding: 18px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  font-size: 18px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  transition: background var(--t-fast), transform 80ms;
  -webkit-tap-highlight-color: transparent;
  user-select: none;
}
.key:hover { background: var(--surface-2); }
.key:active { transform: scale(0.95); background: var(--surface-2); }
</style>
