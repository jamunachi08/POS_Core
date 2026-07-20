# CHANGELOG — v15.5.25

Product goal: keep ALL functionality (all verticals, all-in-one), but make
the process simple enough for a layman, and make the cashier operable
without looking at the screen — accessibility AND visibility.

## Simpler — one obvious path (no functionality removed)
- The Hub now shows an ordered path: **① Start Setup** (the guided wizard)
  and **② Open Cashier** as the first two shortcuts. A new user can't get
  lost between the two old setup screens.
- The old "Bonanza" setup page is reframed as **Advanced Configuration**
  with a big "Run the guided setup wizard" button at the top. All its
  manual-config buttons stay — they're just clearly secondary now.
- One default cashier: the wizard and the Hub both open the Classic
  register. The richer v2 cashier remains available, just not the default.

## Accessible — "drive the register as a blind man"
The Classic register can now be run without watching the screen:
- **Spoken / announced status bar** (`aria-live`): every action is read out
  by screen readers — e.g. "Added LATTE, quantity 1, 14.00 SAR. Total 14.00
  SAR." Quantity changes and removals are announced too.
- **Audio confirmation:** a short beep on a successful add, a low tone on
  empty/removed — so the cashier hears success without looking.
- **Optional Voice mode:** a 🔊 Voice toggle speaks each action aloud (for
  counters without a screen reader). Off by default; remembered per device.
- **Keyboard-first:** the cursor lands in the Scan box on load and returns
  there after every add. Shortcuts: Enter = add, Alt+S = scan box,
  Alt+P = Pay & Submit, Alt+H = Hold, Alt+R = Return, Alt+K = Pay by Card,
  Alt+Backspace = remove last line, Alt+A = Big & Clear, Alt+V = Voice.
  A "⌨ Keys" button lists them.
- **Big & Clear mode:** one toggle (or Alt+A) switches to high-contrast,
  large-text layout with bigger buttons and a large total — for low-vision
  cashiers. Remembered per device.
- **Strong focus ring** on every field and button for keyboard users.

All of this is additive — nothing in the existing sell/pay/hold/return
flow changed; it's just now announced, audible, and keyboard-drivable.
