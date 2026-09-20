<script setup>
import { ref } from 'vue'
import { LOCALES, applyLocale } from '../locales'
import { useI18n } from 'vue-i18n'

const { locale } = useI18n()
const open = ref(false)

function pick(code) {
  applyLocale(code)
  open.value = false
}
</script>

<template>
  <div class="lang-switch" @click.stop>
    <button class="lang-btn" @click="open = !open" :title="$t('app.name')">
      <span class="globe">🌐</span>
      <span class="code">{{ locale.toUpperCase() }}</span>
    </button>
    <div v-if="open" class="lang-menu">
      <button
        v-for="l in LOCALES"
        :key="l.code"
        class="lang-item"
        :class="{ active: l.code === locale }"
        @click="pick(l.code)"
      >
        <span class="native">{{ l.native }}</span>
        <span class="dir">{{ l.dir.toUpperCase() }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.lang-switch { position: relative; }
.lang-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: var(--r-md);
  border: 1px solid var(--border);
  background: var(--surface);
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
}
.lang-btn:hover { background: var(--surface-2); }
.globe { font-size: 13px; }
.lang-menu {
  position: absolute;
  inset-block-start: calc(100% + 6px);
  inset-inline-end: 0;
  min-width: 160px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-md);
  padding: 4px;
  z-index: 1000;
}
.lang-item {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: var(--r-sm);
  background: transparent;
  border: none;
  text-align: start;
  font-size: 13px;
  color: var(--text);
}
.lang-item:hover { background: var(--surface-2); }
.lang-item.active { background: var(--accent-soft); color: var(--accent); font-weight: 500; }
.lang-item .dir {
  font-size: 10px;
  color: var(--text-dim);
  font-family: var(--font-mono);
}
.lang-item.active .dir { color: var(--accent); }
</style>
