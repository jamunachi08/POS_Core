<script setup>
import { computed, onMounted } from 'vue'
import { usePOSStore } from './stores/pos'
import BootScreen from './components/BootScreen.vue'
import CashierView from './views/CashierView.vue'

const store = usePOSStore()

const ready = computed(() => store.boot && !store.bootLoading && !store.bootError)

onMounted(() => {
  // Allow URL ?terminal=XYZ to drive selection
  const url = new URL(window.location.href)
  const fromUrl = url.searchParams.get('terminal')
  if (fromUrl) store.changeTerminal(fromUrl)
  else if (store.terminal) store.loadBoot()
})
</script>

<template>
  <BootScreen v-if="!ready" />
  <CashierView v-else />
</template>
