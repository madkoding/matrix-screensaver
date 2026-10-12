"""Thin ctypes wrappers around the Win32 bits a screensaver needs."""
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
_k32_err = ctypes.WinDLL("kernel32", use_last_error=True)

user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.IsWindow.argtypes = [wintypes.HWND]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]

GWL_STYLE = -16
WS_POPUP, WS_CHILD, WS_VISIBLE = 0x80000000, 0x40000000, 0x10000000
HWND_TOPMOST = wintypes.HWND(-1)
SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x0010, 0x0040
ERROR_ALREADY_EXISTS = 183


def make_dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor
    except Exception:
        user32.SetProcessDPIAware()


def list_monitors():
    """[{x, y, w, h, dpi}] in virtual-desktop pixels; primary first."""
    out = []
    proto = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
        ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    get_dpi = ctypes.windll.shcore.GetDpiForMonitor
    get_dpi.argtypes = [wintypes.HANDLE, ctypes.c_int,
                        ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]

    def cb(hmon, _dc, rect, _lp):
        r = rect.contents
        dx, dy = ctypes.c_uint(96), ctypes.c_uint(96)
        try:
            get_dpi(hmon, 0, ctypes.byref(dx), ctypes.byref(dy))  # effective DPI
        except Exception:
            pass
        scale = min(3.0, max(0.75, dx.value / 96.0))
        out.append(dict(x=r.left, y=r.top, w=r.right - r.left,
                        h=r.bottom - r.top, dpi=scale))
        return True

    user32.EnumDisplayMonitors(None, None, proto(cb), 0)
    out.sort(key=lambda m: (m["x"] != 0 or m["y"] != 0))  # primary at (0,0)
    return out


def monitor_signature(mons):
    return tuple((m["x"], m["y"], m["w"], m["h"], round(m["dpi"], 2)) for m in mons)


def virtual_bounds(mons):
    x = min(m["x"] for m in mons)
    y = min(m["y"] for m in mons)
    w = max(m["x"] + m["w"] for m in mons) - x
    h = max(m["y"] + m["h"] for m in mons) - y
    return x, y, w, h


class _PowerStatus(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                ("BatteryLifeTime", wintypes.DWORD), ("BatteryFullLifeTime", wintypes.DWORD)]


def on_battery():
    st = _PowerStatus()
    if kernel32.GetSystemPowerStatus(ctypes.byref(st)):
        return st.ACLineStatus == 0
    return False


_mutexes = []


def acquire_single_instance(name):
    """False if another process already holds the named mutex."""
    handle = _k32_err.CreateMutexW(None, False, name)
    _mutexes.append(handle)  # keep alive for the life of the process
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS


def is_window(hwnd):
    return bool(user32.IsWindow(hwnd))


def client_size(hwnd):
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    return max(1, r.right - r.left), max(1, r.bottom - r.top)


def embed_in_parent(child, parent, w, h):
    """Turn `child` into a child window of `parent` (screensaver preview pane)."""
    user32.SetParent(child, parent)
    style = user32.GetWindowLongPtrW(child, GWL_STYLE)
    style = (style & ~WS_POPUP) | WS_CHILD | WS_VISIBLE
    user32.SetWindowLongPtrW(child, GWL_STYLE, style)
    user32.SetWindowPos(child, None, 0, 0, w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW)


def set_topmost(hwnd, x, y, w, h):
    user32.SetWindowPos(hwnd, HWND_TOPMOST, x, y, w, h, SWP_SHOWWINDOW)


def message_box(text, title):
    user32.MessageBoxW(None, text, title, 0x40)
