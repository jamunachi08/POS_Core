<script setup>
/**
 * Quick-pick pad — the no-barcode items a grocery cashier reaches for
 * constantly: loose produce, bakery, carrier bags, newspapers.
 *
 * Contents come from `pos.top_movers.get_top_movers`, ranked by how many
 * INVOICES an item appeared on over the window rather than by revenue or
 * units. That matters: bananas outrank a 50 kg rice sack even though the
 * sack is worth more, because the cashier touches bananas forty times a
 * day and the sack twice a month.
 *
 * Deliberately dense and text-first. Product photos look better in a
 * screenshot and are worse in use — at this tile size an image crowds out
 * the name, and the cashier is scanning for a word, not a picture.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  items: { type: Array, default: () => [] },
  tile:  { type: Object, default: () => ({ min: 96, max: 120 }) },
  loading: { type: Boolean, default: false },
})
const emit = defineEmits(['pick'])
const { t } = useI18n()

const gridStyle = computed(() => ({
  gridTemplateColumns: `repeat(auto-fill, minmax(${props.tile.min || 96}px, 1fr))`,
}))

function money(v) {
  const n = Number(v || 0)
  return n.toFixed(2)
}
</script>

<template>
  <section class="tmp">
    <header class="tmp-head">
      <span class="tmp-title">{{ t('supermarket.quick_pick') }}</span>
      <span v-if="items.length" class="tmp-hint">{{ t('supermarket.quick_pick_hint') }}</span>
    </header>

    <div v-if="loading" class="tmp-empty">…</div>

    <div v-else-if="!items.length" class="tmp-empty">
      {{ t('supermarket.quick_pick_empty') }}
    </div>

    <div v-else class="tmp-grid" :style="gridStyle">
      <button
        v-for="it in items"
        :key="it.item_code"
        class="tile"
        :class="{ weighed: it.weighed, pinned: it.pinned }"
        @click="emit('pick', it)"
      >
        <span class="t-name">{{ it.item_name }}</span>
        <span class="t-foot">
          <span class="t-rate">{{ money(it.rate) }}</span>
          <span v-if="it.weighed" class="t-uom">/{{ it.uom }}</span>
        </span>
        <span v-if="it.pinned" class="t-pin" :title="t('supermarket.pinned')">◆</span>
      </button>
    </div>
  </section>
</template>

<style scoped>
.tmp { display: flex; flex-direction: column; gap: 8px; min-height: 0; flex: 1; }

.tmp-head { display: flex; align-items: baseline; gap: 10px; }
.tmp-title { font-size: 11px; color: var(--text-dim); text-transform: uppercase;
  letter-spacing: .6px; font-weight: 600; }
.tmp-hint { font-size: 10.5px; color: var(--text-dim); opacity: .7; }

.tmp-empty { padding: 22px 12px; text-align: center; color: var(--text-dim);
  font-size: 12px; background: var(--surface-2); border-radius: var(--r-sm); }

.tmp-grid { display: grid; gap: 6px; overflow-y: auto; min-height: 0;
  align-content: start; padding-block-end: 4px; }

.tile { position: relative; display: flex; flex-direction: column;
  justify-content: space-between; gap: 4px; min-height: 62px; padding: 8px 9px;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--r-sm); text-align: start; }
.tile:hover  { border-color: var(--accent); }
.tile:active { transform: scale(.97); }

/* A weighed item behaves differently on tap - it reads the scale rather
   than adding qty 1. Flagging it here prevents the cashier hitting it
   twice and wondering why the weight did not change. */
.tile.weighed { border-inline-start: 3px solid var(--accent); }

.t-name { font-size: 12.5px; font-weight: 600; color: var(--text); line-height: 1.25;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; }
.t-foot { display: flex; align-items: baseline; gap: 2px; }
.t-rate { font-size: 13px; font-weight: 700; color: var(--accent);
  font-variant-numeric: tabular-nums; }
.t-uom  { font-size: 10px; color: var(--text-dim); }
.t-pin  { position: absolute; inset-block-start: 4px; inset-inline-end: 5px;
  font-size: 8px; color: var(--accent); opacity: .6; }
</style>
