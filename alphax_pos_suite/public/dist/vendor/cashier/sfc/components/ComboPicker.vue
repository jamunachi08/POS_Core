<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import { useMoney } from '../composables/useMoney'
import AppModal from './AppModal.vue'

// Combo semantics (owner-specified):
//   Fixed        — delivered exactly as configured; this dialog never
//                  opens for Fixed combos (they add straight to cart).
//   Customizable — components flagged allow_substitution may be swapped
//                  for any sellable item in their substitution group;
//                  charge_difference adds (substitute − default) list
//                  price when positive, never a refund when negative.

const props = defineProps({ combo: { type: Object, required: true } })
const emit = defineEmits(['close', 'apply'])
const { t } = useI18n()
const store = usePOSStore()
const { fmt } = useMoney()

const itemByCode = computed(() =>
  Object.fromEntries(store.menuItems.map(i => [i.item_code, i])))

// selection per slot index: chosen item_code (defaults preselected)
const selection = ref(props.combo.components.map(c => c.item_code))

function alternativesFor(comp) {
  if (!comp.allow_substitution || !comp.substitution_item_group) return []
  return store.menuItems.filter(i => i.item_group === comp.substitution_item_group)
}

function priceDelta(comp, chosenCode) {
  if (!comp.charge_difference || chosenCode === comp.item_code) return 0
  const def = itemByCode.value[comp.item_code]
  const alt = itemByCode.value[chosenCode]
  const d = (alt?.standard_rate || 0) - (def?.standard_rate || 0)
  return d > 0 ? d : 0 // a cheaper substitute never discounts the combo
}

const totalDelta = computed(() =>
  props.combo.components.reduce(
    (sum, c, i) => sum + priceDelta(c, selection.value[i]) * (c.qty || 1), 0))

const finalPrice = computed(() => (props.combo.combo_price || 0) + totalDelta.value)

function apply() {
  emit('apply', {
    components: props.combo.components.map((c, i) => ({
      item_code: selection.value[i],
      item_name: itemByCode.value[selection.value[i]]?.item_name || selection.value[i],
      item_group: itemByCode.value[selection.value[i]]?.item_group
        || itemByCode.value[c.item_code]?.item_group,
      qty: c.qty || 1,
      substituted: selection.value[i] !== c.item_code,
      default_item: c.item_code,
    })),
    price: finalPrice.value,
  })
}
</script>

<template>
  <AppModal :title="combo.combo_name" size="md" @close="emit('close')">
    <div class="cp-lead">{{ t('combo.pick_lead') }}</div>

    <div v-for="(comp, i) in combo.components" :key="i" class="cp-slot">
      <div class="cp-slot-h">
        <span>{{ itemByCode[comp.item_code]?.item_name || comp.item_code }}</span>
        <span class="cp-qty">× {{ comp.qty || 1 }}</span>
      </div>
      <div v-if="alternativesFor(comp).length" class="cp-alts">
        <button
          v-for="alt in alternativesFor(comp)"
          :key="alt.item_code"
          class="cp-alt"
          :class="{ active: selection[i] === alt.item_code }"
          @click="selection[i] = alt.item_code"
        >
          {{ alt.item_name }}
          <span v-if="priceDelta(comp, alt.item_code)" class="cp-delta">
            +{{ fmt(priceDelta(comp, alt.item_code)) }}
          </span>
        </button>
      </div>
      <div v-else class="cp-fixed">{{ t('combo.fixed_component') }}</div>
    </div>

    <template #footer>
      <div class="cp-total tnum">{{ fmt(finalPrice) }}</div>
      <button class="btn" @click="emit('close')">{{ t('combo.cancel') }}</button>
      <button class="btn btn-primary" @click="apply">{{ t('combo.add') }}</button>
    </template>
  </AppModal>
</template>

<style scoped>
.cp-lead { color: var(--text-dim); font-size: 13px; margin-block-end: 12px; }
.cp-slot { margin-block-end: 14px; }
.cp-slot-h { display: flex; justify-content: space-between; font-weight: 700; font-size: 14px; margin-block-end: 6px; }
.cp-qty { color: var(--text-dim); font-weight: 500; }
.cp-alts { display: flex; flex-wrap: wrap; gap: 6px; }
.cp-alt {
  padding: 8px 12px; border-radius: var(--r-sm);
  border: 1px solid var(--border); background: var(--surface-2);
  color: var(--text); font-size: 13px; cursor: pointer;
}
.cp-alt.active { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); font-weight: 700; }
.cp-delta { font-size: 11px; color: var(--accent); margin-inline-start: 4px; }
.cp-fixed { font-size: 12px; color: var(--text-dim); }
.cp-total { flex: 1; font-size: 18px; font-weight: 800; align-self: center; }
</style>
