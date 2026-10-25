// In production these are loaded from a server-side endpoint that reads
// the AlphaX POS Settings doctype's modifier configuration. For the demo
// and for items that don't yet have configured modifiers, we synthesize
// a tasteful default for items that look like beverages.
export function modifiersForItem(item) {
  const isBev = /coffee|latte|cappuccino|tea|mocha|drink|juice/i.test(
    item.item_name || item.item_code || '')
  if (!isBev) return []
  return [
    {
      id: 'size', label: 'Size', min: 1, max: 1,
      options: [
        { id: 'sm', label: 'Small',  price_delta: 0 },
        { id: 'md', label: 'Medium', price_delta: 1.5 },
        { id: 'lg', label: 'Large',  price_delta: 3 },
      ]
    },
    {
      id: 'milk', label: 'Milk', min: 1, max: 1,
      options: [
        { id: 'full',  label: 'Whole milk', price_delta: 0 },
        { id: 'skim',  label: 'Skim',       price_delta: 0 },
        { id: 'oat',   label: 'Oat',        price_delta: 1 },
        { id: 'almond',label: 'Almond',     price_delta: 1 },
      ]
    },
    {
      id: 'sugar', label: 'Sugar', min: 0, max: 1,
      options: [
        { id: 'no',  label: 'No sugar',  price_delta: 0 },
        { id: 'reg', label: 'Regular',   price_delta: 0 },
        { id: 'extra',label:'Extra sugar',price_delta: 0 },
      ]
    },
    {
      id: 'extras', label: 'Extras', min: 0, max: 3,
      options: [
        { id: 'shot',  label: 'Extra shot',     price_delta: 2 },
        { id: 'cream', label: 'Whipped cream',  price_delta: 1 },
        { id: 'syrup', label: 'Vanilla syrup',  price_delta: 0.5 },
        { id: 'choc',  label: 'Chocolate dust', price_delta: 0.5 },
      ]
    }
  ]
}
