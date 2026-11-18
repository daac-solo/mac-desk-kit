# mac-desk-kit

The window chrome a macOS desktop widget needs, in one place: a glass
panel that floats above your windows without stealing focus, drags from
anywhere, and comes back where you left it.

Pulled out of two apps that each had their own copy. The copies drifted —
1269 lines apart across two repos before anyone noticed, with the fixes
landing in the one that wasn't running. Only the chrome lives here;
whatever the widget is *for* stays in the widget.

```python
import deskkit as k

panel, ground = k.make_panel(320, 200)   # glass, borderless, floating
ground.on_moved = lambda: k.save_pos("my-app", *panel.frame().origin)
k.place(panel, "my-app")                 # last position, or top right
panel.orderFront_(None)

k.take_focus(panel, text_field)          # only when asked to type
```

| | |
|---|---|
| `make_panel(w, h)` | glass panel + draggable ground; `NSGlassEffectView` where the OS has it |
| `place(panel, app)` | last saved position, or the top right of the screen the pointer is on |
| `save_pos` / `load_pos` | atomic, and `save_pos` returns whether it worked |
| `on_screen(x, y, w, h)` | is this point still reachable? monitors come and go |
| `take_focus(panel, view)` | become key only when asked — a widget that grabs focus is one you turn off |
| `palette(dark)` / `font` / `label` | 南山 / 夜山 as NSColors, read from the brand file |

## Three things this gets right that are easy to get wrong

**A borderless panel refuses key status.** Any text field inside it is
untypable: you click, no caret appears, and your keystrokes go to whatever
app is actually frontmost. Nothing reports an error. `KeyPanel` overrides
`canBecomeKeyWindow`.

**`setMovableByWindowBackground_` never fires** when a glass effect view
fills the panel — it eats the `mouseDown` first. `DragView` starts the
drag on the first `mouseDragged` instead, so clicks still work.

**`NSScreen.mainScreen()` is "the screen with the key window".** A
background app has no key window, so on two monitors a first launch can
land on the other desk. `place` uses the screen the pointer is on.

## Palette

Read at import from `~/tools/signal-flow/brand/tokens.json`, with a
built-in fallback that says so out loud when it is used. Point `BRAND` at
your own file.

## License

MIT
