<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'
import { useSyncStore } from '../stores/sync'
import LocaleSwitch from './LocaleSwitch.vue'
import HardwarePill from './HardwarePill.vue'
import SyncPill from './SyncPill.vue'
import KioskToggle from './KioskToggle.vue'

const props = defineProps({
  collapsed: { type: Boolean, default: false },
})

const store = usePOSStore()
const sync = useSyncStore()
const { t, locale } = useI18n()

const clock = ref('')
let timer = null
function tick() {
  const d = new Date()
  clock.value = d.toLocaleTimeString(locale.value, { hour: '2-digit', minute: '2-digit' })
}
onMounted(() => { tick(); timer = setInterval(tick, 30_000) })
onUnmounted(() => { clearInterval(timer); clearTimeout(hoverTimer) })

const user = computed(() =>
  (window.frappe?.session?.user_fullname) ||
  (window.frappe?.session?.user) || '')

const outletName = computed(() =>
  store.boot?.outlet?.outlet_name || store.boot?.outlet?.name || '')

// ---- hover-expand (mouse users only) --------------------------------------
// The rail is collapsed by policy on touch terminals — hover does not
// exist there and hover-open panels flap when a hand crosses the screen.
// For mouse/trackpad rigs we expand as an OVERLAY after a 300ms intent
// delay: the grid never reflows, and leaving collapses it again.
// Pinning (the toggle button) is the persistent mechanism for everyone.
const hoverOpen = ref(false)
let hoverTimer = null
const canHover = window.matchMedia
  ? window.matchMedia('(hover: hover) and (pointer: fine)').matches
  : false

function onEnter() {
  if (!props.collapsed || !canHover) return
  clearTimeout(hoverTimer)
  hoverTimer = setTimeout(() => { hoverOpen.value = true }, 300)
}
function onLeave() {
  clearTimeout(hoverTimer)
  hoverOpen.value = false
}

// Rail shows icons only when collapsed AND not hover-expanded.
const rail = computed(() => props.collapsed && !hoverOpen.value)

const emit = defineEmits(['toggle-rail', 'open-shift', 'hold', 'recall', 'add-customer', 'scan-loyalty', 'open-floor', 'open-held', 'open-hardware', 'open-queue', 'start-return', 'open-history', 'open-dayclose', 'open-config'])

const bizDateLabel = computed(() => {
  const d = store.businessDate
  if (!d) return ''
  try {
    return new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short' }).format(new Date(d + 'T00:00:00'))
  } catch { return d }
})

function onToggle() {
  hoverOpen.value = false
  clearTimeout(hoverTimer)
  emit('toggle-rail')
}
</script>

<template>
  <aside
    class="sidebar"
    :class="{ rail: rail, 'hover-open': collapsed && hoverOpen }"
    @mouseenter="onEnter"
    @mouseleave="onLeave"
  >
    <div class="brand">
      <div class="brand-mark">α</div>
      <div v-if="!rail" class="brand-text">
        <div class="brand-name">{{ t('app.name') }}</div>
        <div class="brand-outlet">{{ outletName }}</div>
      </div>
      <button
        class="rail-toggle"
        :title="collapsed ? t('sidebar.pin_open') : t('sidebar.collapse')"
        @click="onToggle"
      >{{ rail ? '»' : (collapsed ? '📌' : '«') }}</button>
    </div>

    <div class="quick-actions">
      <div class="qa-group-label" v-if="!rail">{{ t('sidebar.sale') }}</div>
      <div class="qa-divider" v-else></div>
      <!-- Two explicit shift controls with interlocked states:
           Shift In is disabled while a shift is open; Shift Close is
           disabled until one is. Supervisors can act on behalf of a
           cashier inside the dialog. Shift state stays visible even
           on the collapsed rail — it is the most safety-critical
           indicator on this panel. -->
      <div class="sh-pair" :class="{ 'sh-stack': rail }">
        <button class="sh-half sh-in" :disabled="!!store.shift"
          :title="t('shift.btn_in')" @click="$emit('open-shift', 'open')">
          <span class="qa-icon">▶</span>
          <span v-if="!rail">{{ t('shift.btn_in') }}</span>
        </button>
        <button class="sh-half sh-out" :disabled="!store.shift"
          :title="t('shift.btn_close')" @click="$emit('open-shift', 'status')">
          <span class="qa-icon">⏹</span>
          <span v-if="!rail">{{ t('shift.btn_close') }}</span>
        </button>
      </div>
      <div v-if="store.shift && !rail" class="sh-since">
        {{ t('shift.chip_open') }} · {{ store.shift.user }}
      </div>
      <!-- Trading day chip: THE date every sale posts on. Shown even in
           rail mode (title) because after midnight it intentionally
           differs from the wall calendar — that's the feature, and the
           cashier should see it, not be surprised by it. -->
      <div v-if="store.shift" class="sh-bizdate" :class="{ 'bd-rail': rail }"
           :title="t('shift.business_date') + ': ' + bizDateLabel">
        <span class="bd-icon">📅</span>
        <span v-if="!rail">{{ t('shift.business_date_short') }} {{ bizDateLabel }}</span>
      </div>
      <button class="qa-btn" :title="t('cart.add_customer')" @click="$emit('add-customer')">
        <span class="qa-icon">👤</span>
        <span v-if="!rail">{{ t('cart.add_customer') }}</span>
      </button>
      <button
        class="qa-btn"
        :disabled="!store.features.uses_loyalty"
        :title="t('cart.add_loyalty')"
        @click="$emit('scan-loyalty')"
      >
        <span class="qa-icon">⭐</span>
        <span v-if="!rail">{{ t('cart.add_loyalty') }}</span>
      </button>
      <button class="qa-btn" :title="t('cart.hold')" @click="$emit('hold')" :disabled="store.cart.length === 0">
        <span class="qa-icon">⏸</span>
        <span v-if="!rail">{{ t('cart.hold') }}</span>
      </button>
      <button class="qa-btn" :title="t('cart.recall')" @click="$emit('open-held')">
        <span class="qa-icon">↺</span>
        <span v-if="!rail">{{ t('cart.recall') }}</span>
      </button>

      <div class="qa-group-label" v-if="!rail">{{ t('sidebar.order') }}</div>
      <div class="qa-divider" v-else></div>
      <button
        class="qa-btn"
        :disabled="!store.activeFeatures.uses_floor_plan"
        :title="t('table.floor_plan')"
        @click="$emit('open-floor')"
      >
        <span class="qa-icon">⬚</span>
        <span v-if="!rail">{{ t('table.floor_plan') }}</span>
      </button>
      <button
        class="qa-btn"
        :class="{ 'qa-return-active': store.returnMode }"
        :disabled="!store.settings.allow_returns && !store.returnMode"
        :title="store.returnMode ? t('returns.exit') : t('returns.title')"
        @click="$emit('start-return')"
      >
        <span class="qa-icon">↩</span>
        <span v-if="!rail">{{ store.returnMode ? t('returns.exit') : t('returns.title') }}</span>
      </button>
      <!-- View-only sales history: verify + reprint, no mutations. -->
      <button class="qa-btn" :title="t('history.title')" @click="$emit('open-history')">
        <span class="qa-icon">🧾</span>
        <span v-if="!rail">{{ t('history.title') }}</span>
      </button>
      <!-- Day close: terminal-level, supervisor-only (owner decision) —
           it lives here, not inside any shift's Z panel. -->
      <button v-if="store.boot?.is_manager" class="qa-btn" :title="t('dayclose.title')"
              @click="$emit('open-dayclose')">
        <span class="qa-icon">🌙</span>
        <span v-if="!rail">{{ t('dayclose.title') }}</span>
      </button>

      <div class="qa-group-label" v-if="!rail">{{ t('sidebar.system') }}</div>
      <div class="qa-divider" v-else></div>
    </div>

    <div class="spacer"></div>

    <!-- Collapsed rail: two status dots (sync / bridge) so a glance still
         answers "am I online, can I print" without expanding. -->
    <div v-if="rail" class="rail-status">
      <span class="dot" :class="sync.online ? 'dot-ok' : 'dot-bad'"
        :title="sync.online ? t('sync.online') : t('sync.offline_banner')"></span>
    </div>

    <div class="footer" v-if="!rail">
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
  flex: 1;
}

/* Collapsed icon rail */
.sidebar.rail { padding: 14px 8px; gap: 12px; align-items: stretch; }
.sidebar.rail .quick-actions { gap: 6px; }
.sidebar.rail .qa-btn,
.sidebar.rail .sh-half { justify-content: center; padding: 10px 0; }
.sidebar.rail .qa-icon { width: auto; }
.sidebar.rail .brand { flex-direction: column; gap: 6px; padding: 0; }

/* Hover-expanded overlay: floats over the menu grid, grid never reflows */
.sidebar.hover-open {
  position: absolute;
  inset-block: 0;
  inset-inline-start: 0;
  width: 230px;
  z-index: 60;
  box-shadow: 6px 0 22px rgba(0,0,0,0.14);
  border-inline-end: 1px solid var(--border);
}

.brand { display: flex; align-items: center; gap: 10px; padding: 0 4px; position: relative; }
.brand-mark {
  width: 36px; height: 36px;
  border-radius: var(--r-md);
  background: var(--accent);
  color: #fff;
  display: grid; place-items: center;
  font-weight: 600;
  font-size: 18px;
  flex-shrink: 0;
}
.brand-text { min-width: 0; flex: 1; }
.brand-name { font-weight: 600; font-size: 14px; color: var(--text); }
.brand-outlet {
  font-size: 11px; color: var(--text-muted);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.rail-toggle {
  flex-shrink: 0;
  width: 26px; height: 26px;
  border-radius: var(--r-sm, 6px);
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1;
  display: grid; place-items: center;
}
.rail-toggle:hover { background: var(--surface-2); color: var(--accent); border-color: var(--accent); }

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

.rail-status { display: flex; justify-content: center; padding-block-end: 6px; }
.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.dot-ok { background: var(--accent); }
.dot-bad { background: var(--danger); }

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
.qa-group-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  color: var(--text-dim);
  padding: 10px 12px 2px;
}
.qa-group-label:first-child { padding-top: 0; }
.qa-divider { height: 1px; background: var(--border); margin: 6px 4px; }
.sh-pair { display: flex; gap: 6px; padding: 0 6px 4px; }
.sh-pair.sh-stack { flex-direction: column; padding: 0; }
.sh-half {
  flex: 1; min-height: 46px;
  display: flex; align-items: center; justify-content: center; gap: 6px;
  border-radius: var(--r-md);
  font-size: 12px; font-weight: 700;
  border: 1px solid var(--border);
  transition: all 0.12s ease;
}
.sh-pair.sh-stack .sh-half { min-height: 38px; }
.sh-half:disabled { opacity: 0.38; }
.sh-in:not(:disabled) { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
.sh-out:not(:disabled) { background: var(--danger-soft); border-color: var(--danger); color: var(--danger); }
.sh-bizdate {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 600;
  color: var(--accent);
  padding: 2px 4px 8px;
}
.sh-bizdate.bd-rail { justify-content: center; padding: 2px 0 8px; }
.bd-icon { font-size: 12px; }

.sh-since { font-size: 10.5px; color: var(--text-dim); padding: 0 12px 6px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.qa-return-active {
  background: var(--danger-soft);
  border-color: var(--danger);
  color: var(--danger);
  font-weight: 600;
}
</style>
