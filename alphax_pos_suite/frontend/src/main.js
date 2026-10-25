import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { i18n, applyLocale, getStoredLocale } from './locales'
import { useKioskStore } from './stores/kiosk'
import { useSyncStore } from './stores/sync'
import './styles/globals.css'

// Apply locale + dir BEFORE first paint so RTL layout doesn't flash LTR.
applyLocale(getStoredLocale())

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(i18n)

// Install kiosk guards once globally.
const kiosk = useKioskStore(pinia)
kiosk.installGuards()
if (kiosk.on) {
  document.body.classList.add('alphax-kiosk-on')
}

// Boot the offline-sync worker.
const sync = useSyncStore(pinia)
sync.bindConnectivity()
sync.startBackgroundSync(15000)
sync.refreshCounts()
// Also drain on first load if anything is pending and we're online.
if (sync.online) sync.drain().catch(() => {})

app.mount('#alphax-cashier-app')
