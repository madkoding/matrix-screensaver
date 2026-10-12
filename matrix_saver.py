"""Matrix digital rain screensaver for Windows (multi-monitor).

Windows screensaver contract (the .scr is just a renamed .exe):
    /s       run the screensaver full screen
    /c       show the settings dialog
    /p HWND  render inside the tiny preview window of the settings picker

Dev flags:  --seconds N     auto-exit after N seconds (ignores input)
            --shot FILE     save a screenshot just before exiting
            --renderer R    force `gpu` or `software`
"""
import os
import sys
import time

import winapi

MONITOR_CHECK_SECS = 3.0
POWER_CHECK_SECS = 5.0
FPS_AC, FPS_BATTERY = 60, 30
MOUSE_THRESHOLD_PX = 25


# ------------------------------------------------------------------ renderer
def _make_gl(pygame, cfg, mons, origin, size):
    from gl_renderer import GLRenderer
    for attr, val in ((pygame.GL_CONTEXT_MAJOR_VERSION, 3),
                      (pygame.GL_CONTEXT_MINOR_VERSION, 3),
                      (pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)):
        pygame.display.gl_set_attribute(attr, val)
    pygame.display.set_mode(size, pygame.OPENGL | pygame.DOUBLEBUF | pygame.NOFRAME, vsync=1)
    return GLRenderer(mons, cfg, origin, size)


def _make_soft(pygame, cfg, mons, origin, size):
    from soft_renderer import SoftRenderer
    screen = pygame.display.set_mode(size, pygame.NOFRAME)
    return SoftRenderer(mons, cfg, origin, size, screen)


def make_renderer(pygame, cfg, mons, origin, size, preference):
    """GPU first (unless told otherwise), software if OpenGL is unavailable."""
    if preference != "software":
        try:
            return _make_gl(pygame, cfg, mons, origin, size)
        except Exception as exc:  # no GL driver, RDP session, VM...
            print(f"GPU renderer unavailable ({exc}); using software", file=sys.stderr)
            pygame.display.quit()
            pygame.display.init()
    return _make_soft(pygame, cfg, mons, origin, size)


# ------------------------------------------------------------------- session
def run_session(cfg, preview_hwnd=None, seconds=None, shot=None, force=None):
    """Run until the user quits. Returns "quit" or "restart" (monitors changed)."""
    mons = winapi.list_monitors()
    if preview_hwnd:
        pw, ph = winapi.client_size(preview_hwnd)
        mons = [dict(x=0, y=0, w=pw, h=ph, dpi=0.3)]
    sig = winapi.monitor_signature(mons)
    vx, vy, vw, vh = winapi.virtual_bounds(mons)

    os.environ["SDL_VIDEO_WINDOW_POS"] = f"{vx},{vy}"
    os.environ["SDL_VIDEO_ALLOW_SCREENSAVER"] = "1"
    import pygame
    pygame.display.init()
    pygame.font.init()
    renderer = make_renderer(pygame, cfg, mons, (vx, vy), (vw, vh),
                             force or cfg["renderer"])
    pygame.display.set_caption("Matrix Screensaver")
    hwnd = pygame.display.get_wm_info()["window"]
    if preview_hwnd:
        winapi.embed_in_parent(hwnd, preview_hwnd, vw, vh)
    else:
        pygame.mouse.set_visible(False)
        winapi.set_topmost(hwnd, vx, vy, vw, vh)

    clock = pygame.time.Clock()
    start = last_mon = last_pow = time.perf_counter()
    fps_cap = FPS_BATTERY if winapi.on_battery() else FPS_AC
    moved, last_pos, frame, last = 0, None, 0, start
    result = "quit"
    running = True
    while running:
        clock.tick(fps_cap)
        now = time.perf_counter()
        t, dt, last = now - start, min(now - last, 0.1), now

        for e in pygame.event.get():
            if seconds is not None or preview_hwnd:
                continue  # dev/test and preview: input never closes it
            if e.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN, pygame.QUIT):
                running = False
            elif e.type == pygame.MOUSEMOTION:
                if t > 0.6 and last_pos is not None:  # ignore the first jump
                    moved += abs(e.pos[0] - last_pos[0]) + abs(e.pos[1] - last_pos[1])
                    if moved > MOUSE_THRESHOLD_PX:
                        running = False
                last_pos = e.pos

        renderer.render(t, dt, frame)
        pygame.display.flip()
        frame += 1

        if preview_hwnd and not winapi.is_window(preview_hwnd):
            running = False
        if now - last_pow > POWER_CHECK_SECS:
            last_pow = now
            fps_cap = FPS_BATTERY if winapi.on_battery() else FPS_AC
        if not preview_hwnd and now - last_mon > MONITOR_CHECK_SECS:
            last_mon = now
            if winapi.monitor_signature(winapi.list_monitors()) != sig:
                result, running = "restart", False  # hot-plugged a display
        if seconds is not None and t >= seconds:
            if shot:
                renderer.screenshot(shot)
            running = False

    if seconds is not None:
        print(f"renderer: {renderer.name}, avg fps at exit: {clock.get_fps():.1f}")
    renderer.close()
    pygame.display.quit()
    return result


# ---------------------------------------------------------------------- main
def parse_args(argv):
    """-> (mode, preview_hwnd, dev_options)."""
    mode, hwnd = "c", None
    dev = {"seconds": None, "shot": None, "renderer": None}
    i = 0
    while i < len(argv):
        a = argv[i]
        low = a.lower()
        if low in ("--seconds", "--shot", "--renderer") and i + 1 < len(argv):
            key = low[2:]
            dev[key] = float(argv[i + 1]) if key == "seconds" else argv[i + 1]
            mode = "s" if mode == "c" else mode
            i += 2
            continue
        if low[:1] in "/-" and not low.startswith("--") \
                and low.lstrip("/-")[:1] in ("s", "c", "p"):
            body = low.lstrip("/-")
            mode = body[0]
            rest = body[1:].lstrip(":")
            if rest.isdigit():
                hwnd = int(rest)
            elif i + 1 < len(argv) and argv[i + 1].isdigit():
                hwnd = int(argv[i + 1])
                i += 1
        i += 1
    return mode, hwnd, dev


def main():
    mode, hwnd, dev = parse_args(sys.argv[1:])
    if mode == "c":
        import config_dialog
        config_dialog.show()
        return

    if mode == "p" and hwnd is None:
        return  # preview requested without a window to draw into
    winapi.make_dpi_aware()
    if dev["seconds"] is None:
        name = "Local\\MatrixRainScreensaver_" + ("Preview" if mode == "p" else "Run")
        if not winapi.acquire_single_instance(name):
            return  # already running
    import settings
    cfg = settings.load()
    while True:
        res = run_session(cfg, hwnd if mode == "p" else None,
                          dev["seconds"], dev["shot"], dev["renderer"])
        if res != "restart":
            break


if __name__ == "__main__":
    main()
