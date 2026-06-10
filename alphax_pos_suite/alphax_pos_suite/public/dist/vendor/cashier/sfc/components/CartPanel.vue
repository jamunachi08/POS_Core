<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import { useMoney } from '../composables/useMoney'
import { useLongPress } from '../composables/useLongPress'
import { haptics } from '../composables/haptics'
import ContextRibbon from './ContextRibbon.vue'

const store = usePOSStore()
const { t } = useI18n()
const { fmt, fmtNumber } = useMoney()

const emit = defineEmits([
  'pay', 'add-customer', 'scan-loyalty',
  'pick-table', 'add-rx', 'pick-batch', 'pick-appointment',
  'edit-modifiers', 'split-bill', 'line-actions'
])

const earnPoints = computed(() => store.loyaltyQuote?.points || 0)
const earnByItem = computed(() => {
  const m = {}
  for (const b of store.loyaltyQuote?.breakdown || []) {
    if (!b.item_code) continue
    m[b.item_code] = (m[b.item_code] || 0) + b.points
  }
  return m
})

const showSplit = computed(() => store.activeFeatures.uses_split_bill && store.cart.length > 1)

// Build per-line long-press handlers. We bind on the row, but mousedown
// on input/buttons should NOT trigger long-press; the handler checks
// the event target.
function lineHandlers(line) {
  const lp = useLongPress(() => emit('line-actions', line), { delay: 450 })
  // Wrap to skip when target is an interactive sub-element
  const wrapped = {}
  for (const [k, fn] of Object.entries(lp)) {
    wrapped[k] = (e) => {
      const t = e.target
      if (t && (t.tagName === 'INPUT' || t.tagName === 'BUTTON' ||
                t.closest?.('button') || t.closest?.('input'))) {
        return // skip — don't trigger long-press from a control
      }
      fn(e)
    }
  }
  return wrapped
}

function tapPay() {
  haptics.tap()
  emit('pay')
}
</script>

<template>
  <section class="cart-panel">
    <div class="cart-header">
      <div class="customer-line" v-if="!store.customer">
        <div class="walk-in">{{ t('cart.walk_in') }}</div>
        <button class="link" @click="emit('add-customer')">+ {{ t('cart.add_customer') }}</button>
      </div>
      <div class="customer-line" v-else>
        <div class="customer-info">
          <div class="customer-name">{{ store.customer }}</div>
          <div class="customer-meta" v-if="store.wallet">
            <span class="pill pill-accent">
              {{ t('cart.points_balance', { n: fmtNumber(store.wallet.current_balance) }) }}
            </span>
            <span v-if="store.wallet.current_tier" class="pill pill-warn">
              {{ store.wallet.current_tier }}
            </span>
          </div>
        </div>
        <button class="link" @click="store.setCustomer(null)">{{ t('app.remove') }}</button>
      </div>
    </div>

    <ContextRibbon
      @pick-table="emit('pick-table')"
      @add-rx="emit('add-rx')"
      @pick-batch="emit('pick-batch')"
      @pick-appointment="emit('pick-appointment')"
    />

    <div class="cart-body">
      <div v-if="store.cart.length === 0" class="empty">
        <div class="empty-icon">⊕</div>
        <div class="empty-title">{{ t('cart.empty_title') }}</div>
        <div class="empty-sub">{{ t('cart.empty_subtitle') }}</div>
      </div>
      <div v-else class="lines">
        <div
          v-for="line in store.cart"
          :key="line.line_uuid"
          class="line"
          v-bind="lineHandlers(line)"
        >
          <div class="line-top">
            <div class="line-name">
              {{ line.item_name }}
              <button
                v-if="store.activeFeatures.uses_modifiers"
                class="mod-btn"
                @click="emit('edit-modifiers', line)"
                :title="t('cart.edit_modifiers')"
              >⚙</button>
            </div>
            <div class="line-amount tnum">{{ fmt(line.qty * line.rate) }}</div>
          </div>
          <div v-if="line.modifiers && line.modifiers.length" class="line-mods">
            <span v-for="m in line.modifiers" :key="m.option_id" class="mod-pill">
              {{ m.option }}<span v-if="m.price_delta" class="mod-delta tnum">
                {{ m.price_delta > 0 ? '+' : '' }}{{ fmt(m.price_delta) }}
              </span>
            </span>
          </div>
          <div class="line-controls">
            <div class="qty-control">
              <button class="qty-btn" @click="store.changeQty(line.line_uuid, -1)">−</button>
              <input
                class="qty-input tnum"
                type="number"
                step="0.001"
                min="0"
                :value="line.qty"
                @input="store.setQty(line.line_uuid, $event.target.value)"
              />
              <button class="qty-btn" @click="store.changeQty(line.line_uuid, +1)">+</button>
            </div>
            <div class="line-rate tnum">@ {{ fmt(line.rate) }}</div>
            <button class="line-remove" @click="store.removeLine(line.line_uuid)" :title="t('app.remove')">×</button>
          </div>
          <div v-if="earnByItem[line.item_code]" class="line-points">
            {{ t('cart.points_earned', { n: fmtNumber(earnByItem[line.item_code]) }) }}
          </div>
        </div>
      </div>
    </div>

    <div class="cart-totals" v-if="store.cart.length > 0">
      <div class="t-row">
        <span>{{ t('cart.subtotal') }}</span>
        <span class="tnum">{{ fmt(store.subtotal) }}</span>
      </div>
      <div class="t-row" v-if="store.taxAmount > 0">
        <span>{{ t('cart.tax') }} ({{ fmtNumber(store.taxRate, 1) }}%)</span>
        <span class="tnum">{{ fmt(store.taxAmount) }}</span>
      </div>
      <div class="t-row earn" v-if="earnPoints > 0">
        <span>{{ t('cart.loyalty_earn') }}</span>
        <span class="tnum">+{{ fmtNumber(earnPoints) }} pts</span>
      </div>
      <div class="t-row redeem" v-if="store.redeemValue > 0">
        <span>{{ t('cart.loyalty_redeem') }}</span>
        <span class="tnum">− {{ fmt(store.redeemValue) }}</span>
      </div>
      <div class="t-row total">
        <span>{{ t('cart.total') }}</span>
        <span class="tnum">{{ fmt(store.total) }}</span>
      </div>
    </div>

    <div class="action-row">
      <button
        v-if="showSplit"
        class="split-btn"
        @click="emit('split-bill')"
        :title="t('cart.split_bill')"
      >
        {{ t('cart.split_bill') }}
      </button>
      <button
        class="pay-btn"
        :disabled="store.cart.length === 0"
        @click="tapPay"
      >
        {{ store.cart.length === 0
          ? t('cart.pay')
          : t('cart.pay_amount', { amount: fmt(store.total) }) }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.cart-panel {
  background: var(--surface);
  border-inline-start: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.cart-header {
  padding: 14px 18px;
  border-block-end: 1px solid var(--border);
}
.customer-line {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.walk-in { color: var(--text-muted); font-size: 13px; }
.customer-info { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.customer-name {
  font-size: 14px; font-weight: 600; color: var(--text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.customer-meta { display: flex; gap: 4px; flex-wrap: wrap; }
.link {
  background: transparent; border: none;
  color: var(--accent); font-size: 12px; font-weight: 500;
  padding: 4px 0;
}
.link:hover { text-decoration: underline; }

.cart-body { flex: 1; overflow-y: auto; min-height: 0; }
.empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 30px;
  text-align: center;
  color: var(--text-muted);
  gap: 6px;
}
.empty-icon {
  font-size: 42px;
  color: var(--text-dim);
  opacity: 0.4;
  margin-block-end: 12px;
}
.empty-title { font-size: 14px; font-weight: 500; color: var(--text); }
.empty-sub { font-size: 12px; color: var(--text-muted); }

.lines { padding: 6px 0; }
.line {
  padding: 12px 18px;
  border-block-end: 1px solid var(--border);
  user-select: none;
  -webkit-tap-highlight-color: transparent;
}
.line:hover { background: rgba(0,0,0,0.015); }
.line:last-child { border-block-end: none; }
.line-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-block-end: 8px;
}
.line-name {
  font-size: 13px; font-weight: 500; color: var(--text);
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
}
.mod-btn {
  background: transparent;
  border: none;
  width: 22px; height: 22px;
  border-radius: 50%;
  font-size: 12px;
  color: var(--text-dim);
  flex-shrink: 0;
}
.mod-btn:hover { background: var(--surface-2); color: var(--accent); }
.line-mods { display: flex; flex-wrap: wrap; gap: 4px; margin-block: 4px 6px; }
.mod-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: var(--surface-2);
  border-radius: var(--r-pill);
  font-size: 11px;
  color: var(--text-muted);
}
.mod-delta { font-size: 10px; color: var(--accent); }
.line-amount { font-size: 13px; font-weight: 600; color: var(--text); white-space: nowrap; }

.line-controls {
  display: flex;
  align-items: center;
  gap: 10px;
}
.qty-control {
  display: flex;
  align-items: center;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  overflow: hidden;
  background: var(--surface);
}
.qty-btn {
  width: 28px;
  height: 28px;
  background: transparent;
  border: none;
  font-size: 14px;
  color: var(--text);
}
.qty-btn:hover { background: var(--surface-2); }
.qty-input {
  width: 50px;
  height: 28px;
  border: none;
  border-inline: 1px solid var(--border);
  text-align: center;
  font-size: 13px;
  background: transparent;
  outline: none;
}
.qty-input::-webkit-inner-spin-button, .qty-input::-webkit-outer-spin-button {
  -webkit-appearance: none; margin: 0;
}
.line-rate { color: var(--text-muted); font-size: 11px; flex: 1; }
.line-remove {
  background: transparent;
  border: none;
  width: 26px; height: 26px;
  border-radius: 50%;
  color: var(--text-dim);
  font-size: 18px;
  line-height: 1;
}
.line-remove:hover { background: var(--danger-soft); color: var(--danger); }

.line-points {
  display: inline-block;
  margin-block-start: 6px;
  padding: 2px 8px;
  background: var(--accent-soft);
  color: var(--accent);
  border-radius: var(--r-sm);
  font-size: 10px;
  font-weight: 500;
}

.cart-totals {
  padding: 14px 18px;
  border-block-start: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.t-row {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  color: var(--text-muted);
}
.t-row.earn { color: var(--accent); font-weight: 500; }
.t-row.redeem { color: var(--accent); font-weight: 500; }
.t-row.total {
  font-size: 18px;
  font-weight: 600;
  color: var(--text);
  padding-block-start: 8px;
  margin-block-start: 4px;
  border-block-start: 1px solid var(--border);
}

.action-row {
  display: flex;
  gap: 8px;
  margin: 0 18px 18px;
}
.split-btn {
  padding: 16px;
  border-radius: var(--r-md);
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border);
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
}
.split-btn:hover { background: var(--surface-2); border-color: var(--accent); color: var(--accent); }

.pay-btn {
  flex: 1;
  padding: 16px;
  border-radius: var(--r-md);
  background: var(--accent);
  color: #fff;
  border: none;
  font-size: 15px;
  font-weight: 600;
  transition: background var(--t-fast), transform var(--t-fast);
}
.pay-btn:hover:not(:disabled) { background: var(--accent-hover); }
.pay-btn:active:not(:disabled) { transform: scale(0.99); }
.pay-btn:disabled {
  background: var(--surface-2);
  color: var(--text-dim);
  cursor: not-allowed;
}
</style>
