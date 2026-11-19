"""Finds the Windows On-Screen Keyboard so the suggestion bar can sit right above it."""
import ctypes
import logging
import sys

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    from ctypes import wintypes

    user32 = ctypes.windll.user32


def enable_dpi_awareness():
    """Makes window positions line up exactly on high-resolution screens."""
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


MAC_KEYBOARD_HINTS = ("assistive", "accessibilitykeyboard", "accessibility keyboard")
_warned = set()


def _warn_once(key, msg):
    if key not in _warned:
        _warned.add(key)
        logging.warning(msg)


def mac_windows():
    """All on-screen windows as (owner, name, x, y, w, h). Used for docking and the check script."""
    import Quartz

    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    out = []
    for info in Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []:
        b = info.get("kCGWindowBounds") or {}
        out.append((
            str(info.get("kCGWindowOwnerName", "")),
            str(info.get("kCGWindowName", "") or ""),
            *(int(b.get(k, 0)) for k in ("X", "Y", "Width", "Height")),
        ))
    return out


def _mac_keyboard_rect():
    try:
        windows = mac_windows()
    except ImportError:
        _warn_once("quartz", "pyobjc-framework-Quartz is not installed; can't find the Accessibility Keyboard")
        return None
    try:
        import Quartz

        screen = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
        screen_w, screen_h = int(screen.size.width), int(screen.size.height)
    except Exception:
        screen_w, screen_h = 10**6, 10**6
    best = None
    for owner, name, x, y, w, h in windows:
        label = (owner + " " + name).lower()
        if h > 0.7 * screen_h:  # skip the invisible full-screen dwell overlay
            continue
        if not any(hint in label or hint in label.replace(" ", "") for hint in MAC_KEYBOARD_HINTS):
            continue
        if w < 200 or h < 100:  # skip small helper panels
            continue
        if best is None or w * h > best[2] * best[3]:
            best = (x, y, w, h)
    if best:
        x, y, w, h = best
        return x, y, x + w, y + h
    _warn_once("nokbd", "Accessibility Keyboard window not found; docking to the bottom of the screen")
    return None


def find_keyboard_rect(class_names):
    """(left, top, right, bottom) of the visible on-screen keyboard, or None."""
    if sys.platform == "darwin":
        try:
            return _mac_keyboard_rect()
        except Exception:
            logging.exception("Could not find the Accessibility Keyboard")
            return None
    if not IS_WINDOWS:
        return None
    for cls in class_names:
        hwnd = user32.FindWindowW(cls, None)
        if hwnd and user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            rect = wintypes.RECT()
            # The visible edges, without Windows' invisible resize borders, so the bar lines up exactly.
            try:
                if ctypes.windll.dwmapi.DwmGetWindowAttribute(
                        wintypes.HWND(hwnd), 9, ctypes.byref(rect), ctypes.sizeof(rect)) == 0:  # EXTENDED_FRAME_BOUNDS
                    return rect.left, rect.top, rect.right, rect.bottom
            except Exception:
                pass
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return rect.left, rect.top, rect.right, rect.bottom
    return None


def work_area():
    """Screen area not covered by the taskbar, or None."""
    if not IS_WINDOWS:
        return None
    rect = wintypes.RECT()
    if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):  # SPI_GETWORKAREA
        return rect.left, rect.top, rect.right, rect.bottom
    return None


def _run(args):
    import subprocess

    return subprocess.run(args, check=False, capture_output=True, timeout=5,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def launch_keyboard():
    """Opens the Windows On-Screen Keyboard. (macOS only allows this from System Settings.)"""
    try:
        if IS_WINDOWS:
            import os

            os.startfile("osk.exe")
    except Exception:
        logging.exception("Could not open the on-screen keyboard")


def close_keyboard(class_names=("OSKMainClass",)):
    """Closes the on-screen keyboard when OcuSpeak exits."""
    try:
        if IS_WINDOWS:
            for cls in class_names:
                hwnd = user32.FindWindowW(cls, None)
                if hwnd:
                    user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
            if user32.FindWindowW("OSKMainClass", None):
                _run(["taskkill", "/IM", "osk.exe"])
    except Exception:
        logging.exception("Could not close the on-screen keyboard")
