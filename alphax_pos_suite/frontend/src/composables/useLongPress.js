// useLongPress — fires a callback after the user holds a touch / mouse
// down for `delay` ms. Cancels on movement beyond `tolerance` px or release.
//
// Usage in a component:
//   const lp = useLongPress(() => doSomething(line), { delay: 450 })
//   <div v-bind="lp">long-pressable</div>

import { haptics } from './haptics'

export function useLongPress(callback, opts = {}) {
  const delay = opts.delay ?? 500
  const tolerance = opts.tolerance ?? 10

  let timer = null
  let startX = 0, startY = 0
  let fired = false

  function clear() {
    if (timer) { clearTimeout(timer); timer = null }
  }

  function down(e) {
    fired = false
    const t = e.touches?.[0] || e
    startX = t.clientX
    startY = t.clientY
    clear()
    timer = setTimeout(() => {
      fired = true
      haptics.longPress()
      callback(e)
    }, delay)
  }

  function move(e) {
    if (!timer) return
    const t = e.touches?.[0] || e
    const dx = Math.abs(t.clientX - startX)
    const dy = Math.abs(t.clientY - startY)
    if (dx > tolerance || dy > tolerance) clear()
  }

  function up() { clear() }

  function leave() { clear() }

  function contextmenu(e) {
    // Right-click → fire as a long-press too (desktop fallback).
    e.preventDefault()
    fired = true
    callback(e)
  }

  return {
    onMousedown:    down,
    onMousemove:    move,
    onMouseup:      up,
    onMouseleave:   leave,
    onTouchstart:   down,
    onTouchmove:    move,
    onTouchend:     up,
    onTouchcancel:  leave,
    onContextmenu:  contextmenu,
  }
}
