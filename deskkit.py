"""The window chrome a desktop widget needs, owned in one place.

Two apps have wanted the same glass panel that you can drag, that comes
back where you left it, and that follows 南山/夜山. The first time that
happened the whole file was copied instead, and 1269 lines drifted apart
in two repos before anyone noticed — the fixes went into one copy and the
running app was the other.

So only the chrome lives here, and only one copy of it exists. Business
logic stays in each app: a capture inbox and a task list want different
things, which is exactly why they are different apps.

Palette comes from ~/tools/signal-flow/brand/tokens.json, read at import,
so a colour changed in the brand source changes here too.
"""

import io
import json
import os

# Set DESKKIT_TRACE=1 to find out why a widget came up in the wrong place.
_TRACE = os.environ.get("DESKKIT_TRACE") == "1"


def _trace(msg):
    if not _TRACE:
        return
    try:
        with io.open("/tmp/deskkit-trace.log", "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")
    except Exception:
        pass

import AppKit
import objc
from Foundation import NSMakeRect


# --- 南山 / 夜山 ----------------------------------------------------------
# Read, not copied. A palette duplicated into Python is how 瞭望鸡 and the
# website ended up on #c4a882 while Signal Flow was on #00749e, with no
# file saying which was intended.

BRAND = os.path.expanduser("~/tools/signal-flow/brand/tokens.json")

_FALLBACK = {
    "light": {"bg": "#f9f9f8", "paper": "#fdfdfc", "fg": "#1d3e56",
              "muted": "#63635e", "accent": "#00749e", "green": "#2a7e3b",
              "alarm": "#c0481f"},
    "dark":  {"bg": "#111113", "paper": "#b9b6af", "fg": "#eeeeec",
              "muted": "#b0b4ba", "accent": "#75c7f0", "green": "#71d083",
              "alarm": "#ff9478"},
    "radius": 11,
    "type": {"sizes": [11, 13, 17]},
}


def _load_brand():
    try:
        with io.open(BRAND, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:
        # Say it. A palette that silently fell back to hard-coded values
        # looks exactly like one that loaded, right up until the brand
        # changes and this app does not.
        print("deskkit: brand tokens unreadable (%s) — using built-in copy"
              % type(e).__name__, flush=True)
        return _FALLBACK


_B = _load_brand()
SIZES = _B.get("type", {}).get("sizes", [11, 13, 17])
RADIUS = _B.get("radius", 11)


def hexcolor(h, alpha=1.0):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, alpha)


def palette(dark):
    """The token set for one theme, as NSColors."""
    t = _B.get("dark" if dark else "light", _FALLBACK["dark" if dark else "light"])
    out = {}
    for k in ("bg", "paper", "fg", "muted", "accent", "green", "alarm"):
        v = t.get(k)
        out[k] = hexcolor(v) if isinstance(v, str) and v.startswith("#") else None
    return out


def is_dark():
    try:
        name = AppKit.NSApp.effectiveAppearance().bestMatchFromAppearancesWithNames_([
            AppKit.NSAppearanceNameAqua, AppKit.NSAppearanceNameDarkAqua])
        return name == AppKit.NSAppearanceNameDarkAqua
    except Exception:
        return False


def font(size, weight=AppKit.NSFontWeightRegular):
    f = AppKit.NSFont.systemFontOfSize_weight_(size, weight)
    try:
        d = f.fontDescriptor().fontDescriptorWithDesign_(
            AppKit.NSFontDescriptorSystemDesignRounded)
        return AppKit.NSFont.fontWithDescriptor_size_(d, size) or f
    except Exception:
        return f


def label(text, size, color, weight=AppKit.NSFontWeightRegular):
    f = AppKit.NSTextField.labelWithString_(text)
    f.setFont_(font(size, weight))
    f.setTextColor_(color)
    f.setBackgroundColor_(AppKit.NSColor.clearColor())
    return f


# --- where it sits --------------------------------------------------------

def _pos_file(app):
    return os.path.join(os.path.expanduser("~"), ".local", "share", app, "pos.json")


def load_pos(app):
    try:
        with io.open(_pos_file(app), encoding="utf-8") as fh:
            d = json.load(fh)
        return float(d["x"]), float(d["y"])
    except Exception:
        return None


def save_pos(app, x, y):
    """Atomic. A position half-written is a position that reads back as
    corrupt next launch, and the widget silently goes home to the corner
    the author picked."""
    import traceback
    _trace("save_pos(%s, %s) from:\n%s" % (x, y, "".join(traceback.format_stack())))
    try:
        path = _pos_file(app)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"x": float(x), "y": float(y)}, fh)
        os.replace(tmp, path)
        return True
    except Exception as e:
        print("deskkit: position not saved (%s)" % type(e).__name__, flush=True)
        return False


def on_screen(x, y, w, h):
    """Monitors come and go. A point that was on a second display last week
    is off the edge of the world today, and a widget you cannot see is a
    widget you cannot move back."""
    for sc in AppKit.NSScreen.screens():
        vf = sc.visibleFrame()
        if (x + w > vf.origin.x + 40 and x < vf.origin.x + vf.size.width - 40
                and y + h > vf.origin.y + 20
                and y < vf.origin.y + vf.size.height - 20):
            return True
    return False


# --- the draggable ground -------------------------------------------------

class DragView(AppKit.NSView):
    """The panel's background, made draggable.

    setMovableByWindowBackground_ never fires: the glass effect view fills
    the panel and consumes mouseDown before the window sees it.

    The drag starts on the first mouseDragged, not on mouseDown, because
    performWindowDragWithEvent_ swallows the event it is handed. Claiming
    mouseDown would trade every click for a drag that never moved anything.
    """

    def initWithFrame_(self, frame):
        self = objc.super(DragView, self).initWithFrame_(frame)
        if self is not None:
            self.on_moved = None
            self.on_move_start = None
            self.dragging = False
        return self

    # Draggable without first clicking to activate the app it belongs to.
    def acceptsFirstMouse_(self, _event):
        return True

    def mouseDown_(self, event):
        self.dragging = False
        objc.super(DragView, self).mouseDown_(event)

    def mouseDragged_(self, event):
        win = self.window()
        if win is None or self.dragging:
            return
        if not hasattr(win, "performWindowDragWithEvent_"):
            return
        # A drag needs a button actually held down. AppKit delivers
        # mouseDragged at launch with nothing pressed, and handing that to
        # performWindowDragWithEvent_ walks the window over to the pointer
        # and then reports it as "where you put it" — the widget ignored
        # its saved position and overwrote the file with the new one, 104
        # times in one launch. Measured, not guessed: the trace is in the
        # commit.
        if not (AppKit.NSEvent.pressedMouseButtons() & 1):
            return
        self.dragging = True
        if self.on_move_start:
            self.on_move_start()
        win.performWindowDragWithEvent_(event)
        # It returns when the drag ends, so the window is already dropped.
        self.dragging = False
        if self.on_moved:
            self.on_moved()


# --- the panel ------------------------------------------------------------

class KeyPanel(AppKit.NSPanel):
    """A borderless panel refuses key status by default, which leaves any
    text field inside it untypable: you click, the caret appears nowhere,
    and your keystrokes go to whatever app is actually frontmost. Nothing
    reports an error — the widget simply ignores you."""

    def canBecomeKeyWindow(self):
        return True


def make_panel(width, height, radius=None):
    """A borderless floating panel that never takes focus.

    Returns (panel, ground) — put your content in `ground`, which is the
    DragView, so the whole surface drags.
    """
    r = RADIUS + 9 if radius is None else radius
    panel = KeyPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, width, height),
        AppKit.NSWindowStyleMaskBorderless
        | AppKit.NSWindowStyleMaskNonactivatingPanel,
        AppKit.NSBackingStoreBuffered, False)
    # Just under the status bar: high enough to actually be seen every day
    # (a desktop-level panel is hidden the moment any window covers it),
    # low enough that it never steals focus.
    panel.setLevel_(AppKit.NSFloatingWindowLevel)
    panel.setOpaque_(False)
    panel.setBackgroundColor_(AppKit.NSColor.clearColor())
    panel.setHasShadow_(True)
    panel.setAcceptsMouseMovedEvents_(True)
    panel.setCollectionBehavior_(
        AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
        | AppKit.NSWindowCollectionBehaviorStationary
        | AppKit.NSWindowCollectionBehaviorIgnoresCycle)

    pal = palette(is_dark())
    # Liquid glass where the OS has it; the older blur otherwise.
    if hasattr(AppKit, "NSGlassEffectView"):
        blur = AppKit.NSGlassEffectView.alloc().initWithFrame_(
            NSMakeRect(0, 0, width, height))
        blur.setCornerRadius_(r)
        blur.setWantsLayer_(True)
        blur.layer().setMasksToBounds_(True)
        # Glass is the container, not the background. Text needs a ground of
        # its own or a busy wallpaper reads straight through it.
        try:
            blur.setTintColor_(pal["bg"].colorWithAlphaComponent_(
                0.55 if is_dark() else 0.72))
        except Exception:
            pass
    else:
        blur = AppKit.NSVisualEffectView.alloc().initWithFrame_(
            NSMakeRect(0, 0, width, height))
        blur.setMaterial_(AppKit.NSVisualEffectMaterialUnderWindowBackground)
        blur.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
        blur.setState_(AppKit.NSVisualEffectStateActive)
        blur.setWantsLayer_(True)
        blur.layer().setCornerRadius_(r)
        blur.layer().setMasksToBounds_(True)
        blur.layer().setBackgroundColor_(
            pal["bg"].colorWithAlphaComponent_(0.72).CGColor())
    panel.setContentView_(blur)

    ground = DragView.alloc().initWithFrame_(NSMakeRect(0, 0, width, height))
    ground.setWantsLayer_(True)
    ground.setAutoresizingMask_(AppKit.NSViewWidthSizable
                                | AppKit.NSViewHeightSizable)
    blur.addSubview_(ground)
    return panel, ground


def screen_with_mouse():
    """The screen the pointer is on — which is the screen the person is
    looking at. NSScreen.mainScreen() is "the screen with the key window",
    and a background app has no key window, so it answers with whichever
    display happened to have focus last. On two monitors that put a
    first-launch widget on the other desk."""
    p = AppKit.NSEvent.mouseLocation()
    for sc in AppKit.NSScreen.screens():
        f = sc.frame()
        if (f.origin.x <= p.x < f.origin.x + f.size.width
                and f.origin.y <= p.y < f.origin.y + f.size.height):
            return sc
    return AppKit.NSScreen.mainScreen()


class FocusField(AppKit.NSTextField):
    """A text field in a widget you can actually click into.

    A non-activating panel is right for a widget — clicking a checkbox on
    it should not pull you out of what you were doing. But it also means
    clicking the text field does not make the app active, so the caret
    appears and your keystrokes still go somewhere else. Typing looks
    broken and ⌘V does nothing, with no error anywhere.

    So the field, and only the field, asks for focus when clicked.
    """

    def acceptsFirstMouse_(self, _event):
        return True

    def mouseDown_(self, event):
        win = self.window()
        if win is not None:
            take_focus(win, self)
        objc.super(FocusField, self).mouseDown_(event)


def install_menu(quit_title="退出"):
    """Give the app a main menu, so its text fields have a clipboard.

    Cocoa routes ⌘X ⌘C ⌘V ⌘A ⌘Z through the main menu bar. An agent app
    that never built one has no clipboard inside its own text fields at
    all, and nothing reports it: the keystroke simply does nothing.

    The first menu in the bar is the application menu, whatever it is
    called — so the Edit menu has to be the second one, or its shortcuts
    do not register. Building Edit alone looks right and does not work.
    """
    app = AppKit.NSApplication.sharedApplication()
    if app.mainMenu() is not None:
        return
    main = AppKit.NSMenu.alloc().init()

    app_item = AppKit.NSMenuItem.alloc().init()
    main.addItem_(app_item)
    app_menu = AppKit.NSMenu.alloc().init()
    app_menu.addItemWithTitle_action_keyEquivalent_(quit_title, "terminate:", "q")
    app_item.setSubmenu_(app_menu)

    edit_item = AppKit.NSMenuItem.alloc().init()
    main.addItem_(edit_item)
    edit = AppKit.NSMenu.alloc().initWithTitle_("Edit")
    for title, sel, key in (
        ("撤销", "undo:", "z"), ("重做", "redo:", "Z"), (None, None, None),
        ("剪切", "cut:", "x"), ("拷贝", "copy:", "c"),
        ("粘贴", "paste:", "v"), ("全选", "selectAll:", "a"),
    ):
        if title is None:
            edit.addItem_(AppKit.NSMenuItem.separatorItem())
            continue
        edit.addItemWithTitle_action_keyEquivalent_(title, sel, key)
    edit_item.setSubmenu_(edit)

    app.setMainMenu_(main)


def take_focus(panel, view):
    """Become key only when actually asked to type. A desktop widget that
    grabs focus on sight is a widget you turn off."""
    panel.makeKeyAndOrderFront_(None)
    AppKit.NSApp.activateIgnoringOtherApps_(True)
    if view is not None:
        panel.makeFirstResponder_(view)


def place(panel, app, fallback_inset=(24, 24)):
    """Put the panel where it was left, or in the top right of the screen
    the pointer is on if that place is gone."""
    f = panel.frame()
    saved = load_pos(app)
    ok = bool(saved) and on_screen(saved[0], saved[1], f.size.width, f.size.height)
    _trace("place(): saved=%s size=%sx%s on_screen=%s"
           % (saved, f.size.width, f.size.height, ok))
    if ok:
        panel.setFrameOrigin_(AppKit.NSMakePoint(saved[0], saved[1]))
        _trace("place(): set to %s" % (panel.frame().origin,))
        return
    vf = screen_with_mouse().visibleFrame()
    panel.setFrameOrigin_(AppKit.NSMakePoint(
        vf.origin.x + vf.size.width - f.size.width - fallback_inset[0],
        vf.origin.y + vf.size.height - f.size.height - fallback_inset[1]))
