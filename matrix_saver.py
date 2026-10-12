"""Matrix digital rain screensaver for Windows (multi-monitor).

Windows screensaver contract (the .scr is just a renamed .exe):
    /s  -> run the screensaver full screen
    /c  -> show the configuration dialog
    /p  -> render inside the tiny preview window (we simply skip it)

Extra dev flags:  --seconds N   auto-exit after N seconds
                  --shot FILE   save a screenshot just before exiting
"""
import ctypes
import os
import sys
import time
from ctypes import wintypes

import numpy as np

# ---------------------------------------------------------------- look & feel
FONT_SIZE = 26            # px; glyph size on every monitor
CELL_W, CELL_H = 20, 28   # grid cell in px (glyph is centred inside)
FPS = 60
LEVELS = 20               # brightness steps pre-rendered per glyph
BASE_COLOR = (0, 255, 70)       # the film's phosphor green
HEAD_COLOR = (205, 255, 220)    # leading glyph, almost white
SPEED_ROWS_PER_SEC = (9.0, 28.0)
TRAIL_LEN_ROWS = (10, 38)
FLICKER_PER_SEC = 0.35    # fraction of visible cells that mutate each second

# Half-width katakana + a few digits/symbols, all mirrored like the movie.
GLYPHS = (
    [chr(c) for c in range(0xFF66, 0xFF9E)]
    + list("0123456789")
    + list(':.="*+-<>|')
)
SCANLINE_STRENGTH = 0.45  # 0 = off; how dark the odd pixel rows become
INTERLACE_FRAMES = 1      # frames each field stays on (1 = swap every frame)
BLOOM_Q = 4               # bloom is composed at 1/Q resolution
BLOOM_GAIN = 0.15         # 0 = off; strength of the added glow
LATIN_FONT = r"C:\Windows\Fonts\courbd.ttf"  # Courier New Bold
# Depth: three parallax layers drawn far -> near and added together.
#   scale   glyph/cell size vs. the middle layer
#   dim     brightness of the layer (distance haze)
#   speed   fall-speed multiplier (rows/s; pixels/s also grows with scale)
#   density fraction of columns that rain at once
#   trail   trail-length multiplier
#   soft    0..1 defocus blur mixed into the glyphs (near layer = out of focus)
#   glow    whether the layer feeds the bloom
LAYERS = [
    dict(scale=0.65, dim=0.40, speed=0.9, density=0.6, trail=1.2, soft=0.0, glow=False),
    dict(scale=1.00, dim=1.00, speed=1.0, density=0.7, trail=1.0, soft=0.0, glow=True),
    dict(scale=1.80, dim=1.00, speed=0.9, density=0.12, trail=0.5, soft=0.55, glow=True),
]
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msgothic.ttc",
    r"C:\Windows\Fonts\YuGothM.ttc",
    r"C:\Windows\Fonts\meiryo.ttc",
]


def trail_brightness(dist, length):
    """Brightness 0..1 of a cell `dist` rows behind the column head.

    dist   : float array, rows behind the head (negative = not reached yet)
    length : float array broadcastable to dist, trail length of that column

    TODO(human): tune this curve to taste. The default is a gentle
    power-law fade; the film has a bright head, a quick drop, then a long
    dim tail.
    """
    t = np.clip(1.0 - dist / length, 0.0, 1.0)
    return np.where(dist < 0, 0.0, t ** 1.6)


# ------------------------------------------------------------- win32 helpers
user32 = ctypes.windll.user32


def make_dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor
    except Exception:
        user32.SetProcessDPIAware()


def list_monitors():
    """Return [(x, y, w, h), ...] in virtual-desktop pixels."""
    rects = []
    proto = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
        ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    def cb(_m, _dc, r, _l):
        r = r.contents
        rects.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    user32.EnumDisplayMonitors(None, None, proto(cb), 0)
    return rects


def message_box(text, title):
    user32.MessageBoxW(None, text, title, 0x40)


# ------------------------------------------------------------------ glyph art
def load_fonts(size):
    """(latin_font, japanese_font): Courier New Bold, then a CJK fallback."""
    import pygame
    if os.path.exists(LATIN_FONT):
        latin = pygame.font.Font(LATIN_FONT, size)
    else:
        latin = pygame.font.SysFont("couriernew", size, bold=True)
    jp = None
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            jp = pygame.font.Font(path, size)
            break
    if jp is None:
        jp = pygame.font.SysFont("msgothic,yugothic,meiryo", size)
    jp.set_bold(True)  # MS Gothic has no bold face; SDL synthesises it
    return latin, jp


def build_atlas(layer):
    """atlas[level * len(glyphs) + glyph] -> opaque surface (additive-blended).

    Level 0..LEVELS-1 are green ramps, level LEVELS is the near-white head.
    """
    import pygame
    scale, dim, soft = layer["scale"], layer["dim"], layer["soft"]
    cw, ch = round(CELL_W * scale), round(CELL_H * scale)
    latin, jp = load_fonts(round(FONT_SIZE * scale))

    def pick(g):
        # Courier New draws a "tofu" box for katakana instead of reporting
        # the glyph missing, so route by Unicode range, not by metrics().
        f = jp if ord(g) >= 0x3000 else latin
        m = f.metrics(g)
        return f if m and m[0] else None

    pairs = [(g, pick(g)) for g in GLYPHS]
    pairs = [(g, f) for g, f in pairs if f]
    glyphs = [g for g, _ in pairs]

    masters = []
    for g, font in pairs:
        raw = font.render(g, True, (255, 255, 255))
        raw = pygame.transform.flip(raw, True, False)  # mirrored, as in film
        cell = pygame.Surface((cw, ch))
        cell.blit(raw, raw.get_rect(center=(cw // 2, ch // 2)))
        # Glow: blurred copy (down-up scale) added under the sharp glyph.
        small = pygame.transform.smoothscale(cell, (max(1, cw // 3), max(1, ch // 3)))
        halo = pygame.transform.smoothscale(small, (cw, ch))
        halo.fill((110, 110, 110), special_flags=pygame.BLEND_MULT)
        cell.blit(halo, (0, 0), special_flags=pygame.BLEND_ADD)
        if soft > 0:  # defocus: crossfade the sharp glyph with a blurred one
            blur = pygame.transform.smoothscale(
                pygame.transform.smoothscale(cell, (max(1, cw // 2), max(1, ch // 2))),
                (cw, ch))
            blur = pygame.transform.smoothscale(
                pygame.transform.smoothscale(blur, (max(1, cw // 4), max(1, ch // 4))),
                (cw, ch))
            k = int(255 * soft)
            blur.fill((k, k, k), special_flags=pygame.BLEND_MULT)
            cell.fill((255 - k,) * 3, special_flags=pygame.BLEND_MULT)
            cell.blit(blur, (0, 0), special_flags=pygame.BLEND_ADD)
        masters.append(cell.convert())

    def tinted(color):
        out = []
        for m in masters:
            s = m.copy()
            s.fill(color, special_flags=pygame.BLEND_MULT)
            out.append(s)
        return out

    atlas = []
    for lv in range(LEVELS):
        k = ((lv + 1) / LEVELS) ** 1.2 * dim
        atlas += tinted(tuple(int(c * k) for c in BASE_COLOR))
    atlas += tinted(tuple(int(c * dim) for c in HEAD_COLOR))
    return atlas, len(glyphs)


def build_scanlines(w, h):
    """Two opaque BLEND_MULT masks, one per interlace field.

    Field 0 darkens the odd pixel rows, field 1 the even ones; alternating
    them frame by frame gives the shimmering interlaced-CRT look.
    """
    import pygame
    if SCANLINE_STRENGTH <= 0:
        return None
    dark = int(255 * (1 - SCANLINE_STRENGTH))
    masks = []
    for field in (1, 0):
        mask = pygame.Surface((w, h))
        mask.fill((255, 255, 255))
        for y in range(field, h, 2):
            mask.fill((dark, dark, dark), (0, y, w, 1))
        masks.append(mask.convert())
    return masks


# -------------------------------------------------------------------- rain
class Rain:
    """Independent rain field for one monitor."""

    def __init__(self, rect, origin, atlas, n_glyphs, layer, rng):
        import pygame
        self.x, self.y, self.w, self.h = rect
        self.ox, self.oy = self.x - origin[0], self.y - origin[1]
        sc = layer["scale"]
        self.cw, self.ch = round(CELL_W * sc), round(CELL_H * sc)
        self.layer, self.atlas = layer, atlas
        self.cols = self.w // self.cw
        self.rows = self.h // self.ch
        self.pad_x = (self.w - self.cols * self.cw) // 2
        self.gap = self.rows * 0.6 / layer["density"]
        self.speed_rng = tuple(v * layer["speed"] for v in SPEED_ROWS_PER_SEC)
        self.len_rng = tuple(v * layer["trail"] for v in TRAIL_LEN_ROWS)
        self.n = n_glyphs
        self.rng = rng
        c = self.cols
        self.glyph = rng.integers(0, n_glyphs, (self.rows, c))
        self.head = rng.uniform(-self.gap * 2.5, self.rows, c)
        self.speed = rng.uniform(*self.speed_rng, c)
        self.length = rng.uniform(*self.len_rng, c)
        self.row_idx = np.arange(self.rows, dtype=np.float32)[:, None]
        self.col_idx = np.arange(c)
        self.glow_small = pygame.Surface((c, self.rows))
        self.glow_big = pygame.Surface((c * self.cw // BLOOM_Q, self.rows * self.ch // BLOOM_Q))
        self.b = np.zeros((self.rows, c), np.float32)

    def update(self, dt):
        rng = self.rng
        prev = np.floor(self.head).astype(int)
        self.head += self.speed * dt
        # Stamp a fresh random glyph on every row the head crossed.
        cur = np.floor(self.head).astype(int)
        for c in np.nonzero((cur != prev) & (cur >= 0) & (cur < self.rows))[0]:
            self.glyph[cur[c], c] = rng.integers(0, self.n)
        # Recycle columns whose tail has left the screen.
        dead = self.head - self.length > self.rows
        k = int(dead.sum())
        if k:
            self.head[dead] = -rng.uniform(0, self.gap, k)
            self.speed[dead] = rng.uniform(*self.speed_rng, k)
            self.length[dead] = rng.uniform(*self.len_rng, k)
        # Random glyph mutation inside the trails.
        m = int(self.glyph.size * FLICKER_PER_SEC * dt * 0.1)
        if m:
            r = rng.integers(0, self.rows, m)
            cc = rng.integers(0, self.cols, m)
            self.glyph[r, cc] = rng.integers(0, self.n, m)

    def draw(self, screen):
        import pygame
        atlas = self.atlas
        dist = self.head[None, :] - self.row_idx
        b = trail_brightness(dist, self.length[None, :])
        self.b = b
        rows, cols = np.nonzero(b > 0.03)
        if rows.size == 0:
            return
        bv = b[rows, cols]
        lvl = np.minimum((bv * LEVELS).astype(int), LEVELS - 1)
        lvl[dist[rows, cols] < 1.0] = LEVELS  # head
        idx = lvl * self.n + self.glyph[rows, cols]
        xs = cols * self.cw + self.pad_x + self.ox
        ys = rows * self.ch + self.oy
        add = pygame.BLEND_ADD
        screen.blits(
            [(atlas[i], (x, y), None, add)
             for i, x, y in zip(idx.tolist(), xs.tolist(), ys.tolist())],
            doreturn=False)


    def glow(self, low):
        """Bloom: 1 px per cell -> blur on the tiny grid -> add into `low`.

        `low` is the monitor's 1/BLOOM_Q accumulator shared by all layers, so
        the expensive full-size upscale happens once per monitor, not per layer.
        """
        import pygame
        g = self.b
        g = g * g  # only the bright glyphs should bloom
        halo = g * 0.4
        for axis in (0, 1):
            halo[:] += 0.3 * (np.roll(g, 1, axis) + np.roll(g, -1, axis))
        halo += 0.5 * (np.roll(halo, 2, 0) + np.roll(halo, -2, 0)
                       + np.roll(halo, 2, 1) + np.roll(halo, -2, 1)) * 0.5
        rgb = np.clip(halo[..., None] * np.array(BASE_COLOR, np.float32)
                      * BLOOM_GAIN * self.layer["dim"], 0, 255).astype(np.uint8)
        pygame.surfarray.blit_array(self.glow_small, rgb.transpose(1, 0, 2))
        pygame.transform.smoothscale(
            self.glow_small, self.glow_big.get_size(), self.glow_big)
        low.blit(self.glow_big, (self.pad_x // BLOOM_Q, 0),
                 special_flags=pygame.BLEND_ADD)


# -------------------------------------------------------------------- main
def run(seconds=None, shot=None):
    make_dpi_aware()
    mons = list_monitors()
    vx = min(m[0] for m in mons)
    vy = min(m[1] for m in mons)
    vw = max(m[0] + m[2] for m in mons) - vx
    vh = max(m[1] + m[3] for m in mons) - vy

    os.environ["SDL_VIDEO_WINDOW_POS"] = f"{vx},{vy}"
    os.environ["SDL_VIDEO_ALLOW_SCREENSAVER"] = "1"
    import pygame
    pygame.init()
    screen = pygame.display.set_mode((vw, vh), pygame.NOFRAME)
    pygame.display.set_caption("Matrix Screensaver")
    pygame.mouse.set_visible(False)
    try:  # stay above everything, exactly at the virtual-desktop origin
        hwnd = pygame.display.get_wm_info()["window"]
        user32.SetWindowPos(hwnd, -1, vx, vy, vw, vh, 0x0040)
    except Exception:
        pass

    atlases = [build_atlas(layer) for layer in LAYERS]
    scan = build_scanlines(vw, vh)
    frame = 0
    rng = np.random.default_rng()
    lows = [pygame.Surface((m[2] // BLOOM_Q, m[3] // BLOOM_Q)) for m in mons]
    wides = [pygame.Surface((m[2] // BLOOM_Q * BLOOM_Q, m[3] // BLOOM_Q * BLOOM_Q))
             for m in mons]
    fields = [[Rain(m, (vx, vy), atlas, n, layer, rng)
               for layer, (atlas, n) in zip(LAYERS, atlases)] for m in mons]

    clock = pygame.time.Clock()
    start = time.time()
    moved = 0
    last_pos = None
    running = True
    while running:
        dt = min(clock.tick(FPS) / 1000.0, 0.1)
        for e in pygame.event.get():
            if e.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN, pygame.QUIT):
                running = False
            elif seconds is not None:
                continue  # dev/test mode: only the timer ends the run
            elif e.type == pygame.MOUSEMOTION and time.time() - start > 0.6:
                if last_pos is not None:  # ignore the first jump
                    moved += abs(e.pos[0] - last_pos[0]) + abs(e.pos[1] - last_pos[1])
                    if moved > 25:
                        running = False
                last_pos = e.pos
            elif e.type == pygame.MOUSEMOTION:
                last_pos = e.pos
        for layers, low, wide in zip(fields, lows, wides):
            first = layers[0]
            refresh = frame % 2 == 0  # bloom is rebuilt every other frame
            if refresh:
                low.fill((0, 0, 0))
            screen.fill((0, 0, 0), (first.ox, first.oy, first.w, first.h))
            for f in layers:  # far -> near
                f.update(dt)
                f.draw(screen)
                if refresh and BLOOM_GAIN > 0 and f.layer["glow"]:
                    f.glow(low)
            if BLOOM_GAIN > 0:
                if refresh:
                    pygame.transform.scale(low, wide.get_size(), wide)
                screen.blit(wide, (first.ox, first.oy),
                            special_flags=pygame.BLEND_ADD)
        if scan is not None:
            field = (frame // INTERLACE_FRAMES) % 2
            screen.blit(scan[field], (0, 0), special_flags=pygame.BLEND_MULT)
        frame += 1
        pygame.display.flip()
        if seconds is not None and time.time() - start >= seconds:
            if shot:
                pygame.image.save(screen, shot)
            running = False
    fps = clock.get_fps()
    print(f"avg fps at exit: {fps:.1f}")
    pygame.quit()


def main():
    args = [a.lower() for a in sys.argv[1:]]
    mode = args[0].lstrip("/-").split(":")[0] if args else "c"
    if mode == "p":
        return  # preview pane: intentionally blank
    if mode == "c":
        message_box("Matrix Screensaver\n\nNo tiene opciones configurables.",
                    "Matrix Screensaver")
        return
    seconds = shot = None
    if "--seconds" in args:
        seconds = float(args[args.index("--seconds") + 1])
    if "--shot" in sys.argv:
        shot = sys.argv[sys.argv.index("--shot") + 1]
    run(seconds, shot)


if __name__ == "__main__":
    main()
