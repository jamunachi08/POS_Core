<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import LocaleSwitch from './LocaleSwitch.vue'
import HardwarePill from './HardwarePill.vue'
import SyncPill from './SyncPill.vue'
import KioskToggle from './KioskToggle.vue'

const store = usePOSStore()
const { t, locale } = useI18n()

const clock = ref('')
let timer = null
function tick() {
  const d = new Date()
  clock.value = d.toLocaleTimeString(locale.value, { hour: '2-digit', minute: '2-digit' })
}
onMounted(() => { tick(); timer = setInterval(tick, 30_000) })
onUnmounted(() => clearInterval(timer))

const user = computed(() =>
  (window.frappe?.session?.user_fullname) ||
  (window.frappe?.session?.user) || '')

const outletName = computed(() =>
  store.boot?.outlet?.outlet_name || store.boot?.outlet?.name || '')

defineEmits(['hold', 'recall', 'add-customer', 'scan-loyalty', 'open-floor', 'open-held', 'open-hardware', 'open-queue'])
</script>

<template>
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-mark">α</div>
      <div class="brand-text">
        <div class="brand-name">{{ t('app.name') }}</div>
        <div class="brand-outlet">{{ outletName }}</div>
      </div>
    </div>

    <div class="domains">
      <button
        v-for="d in store.boot?.domains || []"
        :key="d.domain_code"
        class="domain"
        :class="{ active: store.activeDomain === d.domain_code }"
        @click="store.switchDomain(d.domain_code)"
      >
        <span class="domain-dot"></span>
        <span class="domain-label">{{ t(`domains.${d.domain_code}`) }}</span>
      </button>
    </div>

    <div class="quick-actions">
      <button class="qa-btn" @click="$emit('add-customer')">
        <span class="qa-icon">👤</span>
        <span>{{ t('cart.add_customer') }}</span>
      </button>
      <button
        class="qa-btn"
        :disabled="!store.features.uses_loyalty"
        @click="$emit('scan-loyalty')"
      >
        <span class="qa-icon">⭐</span>
        <span>{{ t('cart.add_loyalty') }}</span>
      </button>
      <button class="qa-btn" @click="$emit('hold')" :disabled="store.cart.length === 0">
        <span class="qa-icon">⏸</span>
        <span>{{ t('cart.hold') }}</span>
      </button>
      <button class="qa-btn" @click="$emit('open-held')">
        <span class="qa-icon">↺</span>
        <span>{{ t('cart.recall') }}</span>
      </button>
      <button
        class="qa-btn"
        :disabled="!store.activeFeatures.uses_floor_plan"
        @click="$emit('open-floor')"
      >
        <span class="qa-icon">⬚</span>
        <span>{{ t('table.floor_plan') }}</span>
      </button>
    </div>

    <div class="spacer"></div>

    <div class="footer">
      <SyncPill @open-inspector="$emit('open-queue')" />
      <HardwarePill @open-settings="$emit('open-hardware')" />
      <KioskToggle />
      <LocaleSwitch />
      <div class="user-row">
        <div class="user-name">{{ user }}</div>
        <div class="clock tnum">{{ clock }}</div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  background: var(--surface);
  border-inline-end: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 18px 14px;
  gap: 18px;
  min-width: 0;
}

.brand { display: flex; align-items: center; gap: 10px; padding: 0 4px; }
.brand-mark {
  width: 36px; height: 36px;
  border-radius: var(--r-md);
  background: var(--accent);
  color: #fff;
  display: grid; place-items: center;
  font-weight: 600;
  font-size: 18px;
}
.brand-text { min-width: 0; }
.brand-name { font-weight: 600; font-size: 14px; color: var(--text); }
.brand-outlet {
  font-size: 11px; color: var(--text-muted);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

.domains { display: flex; flex-direction: column; gap: 4px; }
.domain {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--r-md);
  background: transparent;
  border: 1px solid transparent;
  text-align: start;
  color: var(--text);
  font-size: 13px;
  font-weight: 500;
  transition: background var(--t-fast);
}
.domain:hover { background: var(--surface-2); }
.domain.active {
  background: var(--accent-soft);
  color: var(--accent);
}
.domain-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--text-dim);
  transition: background var(--t-fast), transform var(--t-fast);
}
.domain.active .domain-dot { background: var(--accent); transform: scale(1.4); }

.quick-actions { display: flex; flex-direction: column; gap: 4px; }
.qa-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: var(--r-md);
  background: transparent;
  border: 1px solid transparent;
  color: var(--text);
  font-size: 13px;
  text-align: start;
  transition: background var(--t-fast);
}
.qa-btn:hover:not(:disabled) { background: var(--surface-2); }
.qa-btn:disabled { color: var(--text-dim); cursor: not-allowed; }
.qa-icon { font-size: 14px; width: 18px; text-align: center; }

.spacer { flex: 1; }

.footer {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-block-start: 12px;
  border-block-start: 1px solid var(--border);
}
.user-row {
  display: flex;
  flex-direction: column;
  font-size: 11px;
  color: var(--text-muted);
}
.user-name {
  font-size: 12px;
  color: var(--text);
  font-weight: 500;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.clock { color: var(--text-dim); font-size: 11px; }
</style>
