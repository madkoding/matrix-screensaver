"""Software (CPU) renderer, used when OpenGL is unavailable (e.g. Remote
Desktop or some VMs). Same look as the GPU path with fewer frills: no flicker,
and the bloom is composed at reduced resolution.
"""
import numpy as np
import pygame

import glyphs
from easter_egg import EasterEgg
from settings import (CELL_H, CELL_W, COLORS, FONT_SIZE, SPEED_ROWS_PER_SEC,
                      TRAIL_LEN_ROWS, active_layers)

LEVELS = 20            # brightness steps pre-rendered per glyph
BLOOM_Q = 4            # bloom is composed at 1/Q resolution
FLICKER_PER_SEC = 0.35


def trail_brightness(dist, length, falloff):
    """Brightness 0..1 of a cell `dist` rows behind the column head."""
    t = np.clip(1.0 - dist / length, 0.0, 1.0)
    return np.where(dist < 0, 0.0, t ** falloff)


def build_atlas(layer, base, head, custom):
    """atlas[level * n + glyph] -> opaque surface (additive-blended).

    Levels 0..LEVELS-1 are the brightness ramp, level LEVELS is the head.
    """
    scale, dim, soft = layer["scale"], layer["dim"], layer["soft"]
    cw, ch = max(4, round(CELL_W * scale)), max(6, round(CELL_H * scale))
    latin, jp = glyphs.load_fonts(max(6, round(FONT_SIZE * scale)), custom)
    pairs = glyphs.pick_glyphs(latin, jp, bool(custom))

    masters = []
    for g, font in pairs:
        cell = glyphs.render_mirrored(g, font, cw, ch)
        # Glow: blurred copy (down-up scale) added under the sharp glyph.
        small = pygame.transform.smoothscale(cell, (max(1, cw // 3), max(1, ch // 3)))
        halo = pygame.transform.smoothscale(small, (cw, ch))
        halo.fill((110, 110, 110), special_flags=pygame.BLEND_MULT)
        cell.blit(halo, (0, 0), special_flags=pygame.BLEND_ADD)
        if soft > 0:  # defocus: crossfade the sharp glyph with a blurred one
            blur = pygame.transform.smoothscale(
                pygame.transform.smoothscale(cell, (max(1, cw // 4), max(1, ch // 4))),
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
        atlas += tinted(tuple(int(c * k) for c in base))
    atlas += tinted(tuple(int(c * dim) for c in head))
    return atlas, len(pairs), (cw, ch)


def build_masks(size, mons, origin, scan, interlace, vig):
    """BLEND_MULT masks: scanlines (one per interlace field) with the
    per-monitor vignette baked in. None when both effects are off."""
    if scan <= 0 and vig <= 0:
        return None
    vw, vh = size
    vign = np.ones((vw, vh), np.float32)
    for m in mons:
        xs = (np.arange(m["w"]) / m["w"] - 0.5) * 2
        ys = (np.arange(m["h"]) / m["h"] - 0.5) * 2
        d = np.sqrt(xs[:, None] ** 2 + ys[None, :] ** 2)
        x = np.clip((d - 0.35) / (1.45 - 0.35), 0, 1)
        v = 1.0 - vig * (x * x * (3 - 2 * x))
        x0, y0 = m["x"] - origin[0], m["y"] - origin[1]
        vign[x0:x0 + m["w"], y0:y0 + m["h"]] = v
    rows = np.arange(vh)
    masks = []
    for field in ((0, 1) if interlace else (0,)):
        line = np.where((rows + field) % 2 == 0, 1.0 - scan, 1.0)
        arr = (vign * line[None, :] * 255).astype(np.uint8)
        surf = pygame.Surface((vw, vh))
        pygame.surfarray.blit_array(surf, np.repeat(arr[:, :, None], 3, axis=2))
        masks.append(surf.convert())
    return masks


class Rain:
    """Independent rain field for one monitor and one depth layer."""

    def __init__(self, mon, origin, atlas, n_glyphs, cell, layer, falloff, base, rng):
        self.ox, self.oy = mon["x"] - origin[0], mon["y"] - origin[1]
        self.w, self.h = mon["w"], mon["h"]
        self.cw, self.ch = cell
        self.layer, self.atlas, self.base = layer, atlas, base
        self.falloff = falloff
        self.cols = self.w // self.cw
        self.rows = self.h // self.ch
        self.pad_x = (self.w - self.cols * self.cw) // 2
        self.n = n_glyphs
        self.rng = rng
        c = self.cols
        self.gap = self.rows * 0.6 / layer["density"]
        self.speed_rng = tuple(v * layer["speed"] for v in SPEED_ROWS_PER_SEC)
        self.len_rng = tuple(v * layer["trail"] for v in TRAIL_LEN_ROWS)
        self.glyph = rng.integers(0, n_glyphs, (self.rows, c))
        self.head = rng.uniform(-self.gap * 2.5, self.rows, c)
        self.speed = rng.uniform(*self.speed_rng, c)
        self.length = rng.uniform(*self.len_rng, c)
        self.row_idx = np.arange(self.rows, dtype=np.float32)[:, None]
        self.glow_small = pygame.Surface((c, self.rows))
        self.glow_big = pygame.Surface((c * self.cw // BLOOM_Q, self.rows * self.ch // BLOOM_Q))
        self.b = np.zeros((self.rows, c), np.float32)
        self.glows = layer["dim"] >= 0.9  # the dim far layer doesn't bloom

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
        dist = self.head[None, :] - self.row_idx
        b = trail_brightness(dist, self.length[None, :], self.falloff)
        self.b = b
        rows, cols = np.nonzero(b > 0.03)
        if rows.size == 0:
            return
        lvl = np.minimum((b[rows, cols] * LEVELS).astype(int), LEVELS - 1)
        lvl[dist[rows, cols] < 1.0] = LEVELS  # head
        idx = lvl * self.n + self.glyph[rows, cols]
        xs = cols * self.cw + self.pad_x + self.ox
        ys = rows * self.ch + self.oy
        add = pygame.BLEND_ADD
        screen.blits(
            [(self.atlas[i], (x, y), None, add)
             for i, x, y in zip(idx.tolist(), xs.tolist(), ys.tolist())],
            doreturn=False)

    def glow(self, low, gain):
        """Bloom: 1 px per cell -> blur on the tiny grid -> add into `low`."""
        g = self.b * self.b  # only the bright glyphs should bloom
        halo = g * 0.4
        for axis in (0, 1):
            halo[:] += 0.3 * (np.roll(g, 1, axis) + np.roll(g, -1, axis))
        halo += 0.25 * (np.roll(halo, 2, 0) + np.roll(halo, -2, 0)
                        + np.roll(halo, 2, 1) + np.roll(halo, -2, 1))
        rgb = np.clip(halo[..., None] * np.array(self.base, np.float32)
                      * gain * self.layer["dim"], 0, 255).astype(np.uint8)
        pygame.surfarray.blit_array(self.glow_small, rgb.transpose(1, 0, 2))
        pygame.transform.smoothscale(
            self.glow_small, self.glow_big.get_size(), self.glow_big)
        low.blit(self.glow_big, (self.pad_x // BLOOM_Q, 0),
                 special_flags=pygame.BLEND_ADD)


class SoftRenderer:
    name = "software"

    def __init__(self, mons, cfg, origin, size, screen):
        self.cfg, self.mons, self.origin, self.size = cfg, mons, origin, size
        self.screen = screen
        base, head = COLORS[cfg["color"]]
        self.base, self.head = base, head
        custom = glyphs.custom_font_path(cfg["font_path"])
        rng = np.random.default_rng()
        cache = {}
        self.fields = []
        for mon in mons:
            mscale = mon["dpi"] * cfg["glyph_scale"]
            layers = []
            for layer in active_layers(cfg):
                lay = dict(layer, scale=layer["scale"] * mscale)
                key = (round(lay["scale"], 3), lay["dim"], lay["soft"])
                if key not in cache:
                    cache[key] = build_atlas(lay, base, head, custom)
                atlas, n, cell = cache[key]
                layers.append(Rain(mon, origin, atlas, n, cell, lay,
                                   cfg["trail_falloff"], base, rng))
            low = pygame.Surface((mon["w"] // BLOOM_Q, mon["h"] // BLOOM_Q))
            wide = pygame.Surface((mon["w"] // BLOOM_Q * BLOOM_Q,
                                   mon["h"] // BLOOM_Q * BLOOM_Q))
            self.fields.append((layers, low, wide))
        self.gain = cfg["bloom"] * 0.3
        self.masks = build_masks(size, mons, origin, cfg["scanlines"],
                                 cfg["interlace"], cfg["vignette"])
        self.egg = EasterEgg(cfg["easter_egg"])
        self.text = None

    def render(self, t, dt, frame):
        screen = self.screen
        refresh = frame % 2 == 0  # bloom is rebuilt every other frame
        for layers, low, wide in self.fields:
            first = layers[0]
            screen.fill((0, 0, 0), (first.ox, first.oy, first.w, first.h))
            if refresh:
                low.fill((0, 0, 0))
            for f in layers:  # far -> near
                f.update(dt)
                f.draw(screen)
                if refresh and self.gain > 0 and f.glows:
                    f.glow(low, self.gain)
            if self.gain > 0:
                if refresh:
                    pygame.transform.scale(low, wide.get_size(), wide)
                screen.blit(wide, (first.ox, first.oy), special_flags=pygame.BLEND_ADD)
        self._draw_egg(t)
        if self.masks:
            screen.blit(self.masks[frame % len(self.masks)], (0, 0),
                        special_flags=pygame.BLEND_MULT)

    def _draw_egg(self, t):
        state = self.egg.update(t)
        if state is None:
            return
        text, shown, alpha, cursor = state
        mon = self.mons[0]
        height = int(mon["h"] * 0.05 * mon["dpi"] ** 0.5)
        if self.text is None or self.text[0] != text:
            font = glyphs.text_font(height)
            self.text = (text, font.render(text, True, self.head, (0, 0, 0)))
        surf = self.text[1]
        tw, th = surf.get_size()
        x = mon["x"] - self.origin[0] + int(mon["w"] * 0.10)
        y = mon["y"] - self.origin[1] + int(mon["h"] * 0.42)
        pad = int(height * 0.6)
        back = pygame.Surface((tw + pad * 2 + height, th + int(pad * 1.2)), pygame.SRCALPHA)
        back.fill((0, 0, 0, int(225 * alpha)))
        self.screen.blit(back, (x - pad, y - int(pad * 0.6)))
        fade = surf.copy()
        k = int(255 * alpha)
        fade.fill((k, k, k), special_flags=pygame.BLEND_MULT)
        cw = tw / len(text)
        self.screen.blit(fade, (x, y), (0, 0, int(cw * shown), th),
                         special_flags=pygame.BLEND_ADD)
        if cursor:
            self.screen.fill(tuple(int(c * alpha) for c in self.base),
                             (x + int(cw * shown), y + int(th * 0.12),
                              int(cw * 0.8), int(th * 0.76)), special_flags=pygame.BLEND_ADD)

    def screenshot(self, path):
        pygame.image.save(self.screen, path)

    def close(self):
        pass
