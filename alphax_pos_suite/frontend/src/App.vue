<script setup>
import { computed, onMounted } from 'vue'
import { usePOSStore } from './stores/pos'
import BootScreen from './components/BootScreen.vue'
import OnboardingWizard from './components/OnboardingWizard.vue'
import CashierView from './views/CashierView.vue'

const store = usePOSStore()
const ready = computed(() => store.boot && !store.bootLoading && !store.bootError)

// Escape hatch: ?classicboot=1 falls back to the plain terminal picker,
// so a station can be recovered without a deploy if the wizard misbehaves.
const classicBoot = new URL(window.location.href).searchParams.get('classicboot') === '1'

onMounted(() => {
  // Allow URL ?terminal=XYZ to drive selection
  const url = new URL(window.location.href)
  const fromUrl = url.searchParams.get('terminal')
  if (fromUrl) store.changeTerminal(fromUrl)
  else if (store.terminal) store.loadBoot()
})
</script>

<template>
  <div class="alphax-root" :data-theme="store.theme">
    <BootScreen v-if="!ready && classicBoot" />
    <OnboardingWizard v-else-if="!ready" />
    <CashierView v-else />
  </div>
</template>

<style scoped>
.alphax-root { display: contents; }
</style>