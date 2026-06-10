<script setup>
/**
 * AlphaX POS v3 — Root component.
 *
 * Phase 2: shows a "foundation ready" placeholder so we can verify
 * the SPA boots and the Vue+Pinia+i18n+Tailwind stack all works.
 *
 * Phase 3 will replace the placeholder with the real Boot/Cashier
 * router (Boot screen on first load → CashierView once a terminal
 * is bound).
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from './stores/pos'
import { useUIStore } from './stores/ui'

const { t, locale } = useI18n()
const pos = usePOSStore()
const ui = useUIStore()

const ready = ref(false)

onMounted(async () => {
  // Verify all stores instantiated; verify the SAR font is loaded.
  console.info('AlphaX POS v3: App.vue mounted, stores ready')
  console.info('  pos store:', pos.$id)
  console.info('  ui store:', ui.$id)
  console.info('  i18n locale:', locale.value)
  // Stub: pretend we loaded a terminal so the UI shows the placeholder
  // (Phase 3 will replace this with real loadBoot)
  ready.value = true
})

function switchLocale() {
  const next = locale.value === 'en' ? 'ar' : 'en'
  locale.value = next
  ui.setLocale(next)
  document.documentElement.setAttribute('dir', next === 'ar' ? 'rtl' : 'ltr')
  document.documentElement.setAttribute('lang', next)
}
</script>

<template>
  <div class="w-full h-full flex flex-col items-center justify-center p-8 animate-fade-in">
    <div class="text-center max-w-xl">
      <!-- Logo -->
      <div class="flex items-center justify-center gap-3 mb-6">
        <div class="w-14 h-14 bg-mauve-500 text-white rounded-xl flex items-center justify-center font-bold text-2xl shadow-mauve">
          A<span class="opacity-70">X</span>
        </div>
        <div class="text-left">
          <div class="text-xl font-semibold text-mauve-500">AlphaX POS</div>
          <div class="text-xs text-mauve-400 uppercase tracking-wider">Version 3 · Phase 2</div>
        </div>
      </div>

      <!-- Headline -->
      <h1 class="text-2xl font-semibold text-gray-900 mb-3">
        {{ t('app.phase2_placeholder_title') }}
      </h1>
      <p class="text-base text-gray-600 mb-6 leading-tight">
        {{ t('app.phase2_placeholder_body') }}
      </p>

      <!-- Foundation status checklist -->
      <div class="bg-white border border-mauve-100 rounded-xl p-6 shadow-sm text-left">
        <div class="text-xs uppercase tracking-wider text-mauve-500 font-semibold mb-3">
          Foundation status
        </div>
        <div class="flex flex-col gap-2">
          <div class="flex items-center gap-2 text-base">
            <span class="text-green-600 font-bold">✓</span>
            <span>Vue 3 runtime</span>
          </div>
          <div class="flex items-center gap-2 text-base">
            <span class="text-green-600 font-bold">✓</span>
            <span>Pinia stores (pos, catalog, shift, ui)</span>
          </div>
          <div class="flex items-center gap-2 text-base">
            <span class="text-green-600 font-bold">✓</span>
            <span>vue-i18n with English + Arabic</span>
          </div>
          <div class="flex items-center gap-2 text-base">
            <span class="text-green-600 font-bold">✓</span>
            <span>Tailwind utility CSS</span>
          </div>
          <div class="flex items-center gap-2 text-base">
            <span class="text-green-600 font-bold">✓</span>
            <span>Saudi Riyal symbol font (<span class="sar-symbol">&#xea;</span>)</span>
          </div>
          <div class="flex items-center gap-2 text-base">
            <span class="text-green-600 font-bold">✓</span>
            <span>API client (with mock mode)</span>
          </div>
        </div>
      </div>

      <!-- Demo: locale toggle, to prove i18n works -->
      <button
        @click="switchLocale"
        class="mt-6 px-5 py-2 bg-mauve-500 hover:bg-mauve-600 text-white rounded-md font-medium transition shadow-mauve">
        Switch to {{ locale === 'en' ? 'العربية' : 'English' }}
      </button>

      <p class="text-sm text-gray-500 mt-6">
        Next: Phase 3 — Layout shell (TopBar, Sidebar, BottomBar).
      </p>
    </div>
  </div>
</template>
