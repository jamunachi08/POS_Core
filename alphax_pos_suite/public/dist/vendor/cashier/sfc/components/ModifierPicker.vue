<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMoney } from '../composables/useMoney'
import AppModal from './AppModal.vue'

const props = defineProps({
  itemName: String,
  baseRate: { type: Number, default: 0 },
  groups: { type: Array, default: () => [] }
})
const emit = defineEmits(['close', 'apply'])
const { t } = useI18n()
const { fmt } = useMoney()

const selections = ref({})
for (const g of props.groups) {
  selections.value[g.id] = []
  if (g.min === 1 && g.max === 1 && (g.options || []).length) {
    selections.value[g.id] = [g.options[0].id]
  }
}

function toggle(group, opt) {
  const current = selections.value[group.id] || []
  if (current.includes(opt.id)) {
    selections.value[group.id] = current.filter(x => x !== opt.id)
    return
  }
  if (group.max === 1) {
    selections.value[group.id] = [opt.id]
  } else {
    if (group.max && current.length >= group.max) return
    selections.value[group.id] = [...current, opt.id]
  }
}

const totalDelta = computed(() => {
  let s = 0
  for (const g of props.groups) {
    for (const optId of (selections.value[g.id] || [])) {
      const o = (g.options || []).find(o => o.id === optId)
      if (o) s += Number(o.price_delta) || 0
    }
  }
  return s
})

const finalRate = computed(() => +(props.baseRate + totalDelta.value).toFixed(2))

const valid = computed(() => {
  for (const g of props.groups) {
    const n = (selections.value[g.id] || []).length
    if (g.min && n < g.min) return false
    if (g.max && n > g.max) return false
  }
  return true
})

function apply() {
  if (!valid.value) return
  const flat = []
  for (const g of props.groups) {
    for (const optId of (selections.value[g.id] || [])) {
      const o = (g.options || []).find(o => o.id === optId)
      if (o) flat.push({
        group: g.label, group_id: g.id,
        option: o.label, option_id: o.id,
        price_delta: Number(o.price_delta) || 0
      })
    }
  }
  emit('apply', { base_rate: props.baseRate, options: flat })
}

function constraintLabel(g) {
  if (g.min === 1 && g.max === 1) return t('modifiers.pick_one')
  if (g.max && g.max > 1) return t('modifiers.pick_up_to', { n: g.max })
  if (g.min && g.min >= 1) return t('modifiers.pick_at_least', { n: g.min })
  return t('modifiers.optional')
}
</script>

<template>
  <AppModal :title="itemName || t('modifiers.title')" size="md" @close="emit('close')">
    <div v-if="groups.length === 0" class="muted">{{ t('modifiers.optional') }}</div>

    <div v-for="g in groups" :key="g.id" class="group">
      <div class="group-head">
        <div class="group-title">{{ g.label }}</div>
        <div class="group-meta">
          <span v-if="g.min" class="pill pill-warn">{{ t('modifiers.required') }}</span>
          <span class="constraint">{{ constraintLabel(g) }}</span>
        </div>
      </div>
      <div class="options">
        <button
          v-for="o in g.options || []"
          :key="o.id"
          class="option"
          :class="{ active: (selections[g.id] || []).includes(o.id) }"
          @click="toggle(g, o)"
        >
          <span class="opt-name">{{ o.label }}</span>
          <span v-if="o.price_delta" class="opt-delta tnum">
            {{ o.price_delta > 0 ? '+' : '' }}{{ fmt(o.price_delta) }}
          </span>
        </button>
      </div>
    </div>

    <template #footer>
      <div class="footer-total tnum">{{ fmt(finalRate) }}</div>
      <button class="btn" @click="emit('close')">{{ t('app.cancel') }}</button>
      <button class="btn btn-primary" :disabled="!valid" @click="apply">
        {{ t('modifiers.add_to_order') }}
      </button>
    </template>
  </AppModal>
</template>

<style scoped>
.muted { color: var(--text-dim); padding: 30px; text-align: center; font-size: 13px; }

.group { margin-block-end: 18px; }
.group:last-child { margin-block-end: 0; }
.group-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-block-end: 8px;
}
.group-title { font-size: 13px; font-weight: 600; color: var(--text); }
.group-meta { display: flex; gap: 6px; align-items: center; }
.constraint { font-size: 11px; color: var(--text-muted); }

.options { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.option {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-radius: var(--r-md);
  background: var(--surface);
  border: 1px solid var(--border);
  font-size: 13px;
  color: var(--text);
  text-align: start;
  transition: border-color var(--t-fast), background var(--t-fast);
}
.option:hover { background: var(--surface-2); border-color: var(--accent); }
.option.active {
  background: var(--accent-soft);
  border-color: var(--accent);
  color: var(--accent);
  font-weight: 500;
}
.opt-name { flex: 1; }
.opt-delta { font-size: 11px; color: var(--text-muted); }
.option.active .opt-delta { color: var(--accent); }

.footer-total {
  margin-inline-end: auto;
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
}
</style>
