import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePOSStore } from '../stores/pos'

export function useMoney() {
  const store = usePOSStore()
  const { locale } = useI18n()

  const currency = computed(() => store.boot?.currency?.currency || 'USD')
  const symbol = computed(() => store.boot?.currency?.symbol || '$')

  function fmt(value) {
    const v = Number(value || 0)
    try {
      return new Intl.NumberFormat(locale.value, {
        style: 'currency',
        currency: currency.value,
        currencyDisplay: 'symbol',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(v)
    } catch {
      return `${symbol.value} ${v.toFixed(2)}`
    }
  }

  function fmtNumber(value, fraction = 0) {
    return new Intl.NumberFormat(locale.value, {
      minimumFractionDigits: fraction,
      maximumFractionDigits: fraction,
    }).format(Number(value || 0))
  }

  return { currency, symbol, fmt, fmtNumber }
}
