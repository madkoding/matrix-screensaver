"""GPU renderer: the whole rain is computed procedurally in a fragment shader.

Pipeline per frame
    scene   -> RGBA8 texture covering the virtual desktop (rain layers + text)
    bloom   -> 1/4 and 1/16 resolution blurs of the scene
    final   -> scene + bloom, vignette, flicker and animated interlaced
               scanlines, straight to the window
"""
import numpy as np
import moderngl
import pygame

import glyphs
from easter_egg import EasterEgg
from fsr import FSR
from settings import (CELL_H, CELL_W, COLORS, FONT_SIZE, SPEED_ROWS_PER_SEC,
                      TRAIL_LEN_ROWS, UPSCALE_RATIO, active_layers)

MAX_MON = 8
MAX_LAYERS = 4
# Atlas cell = glyph area (80x112, the 20:28 grid-cell aspect) + 8 px margin.
ATLAS_CELL = (96, 128)
ATLAS_MARGIN = (8, 8)
ATLAS_FONT = FONT_SIZE * 4

FULLSCREEN_VS = """
#version 330
out vec2 uv;
void main() {
    vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    uv = p;
    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}
"""

SCENE_FS = """
#version 330
uniform vec2 u_res;
uniform float u_time;
uniform int u_nmon;
uniform vec4 u_mon[%(MAX_MON)d];       // x, y, w, h  (top-left origin, px)
uniform float u_dpi[%(MAX_MON)d];
uniform int u_nlay;
uniform vec4 u_lay0[%(MAX_LAYERS)d];   // scale, dim, speed, density
uniform vec4 u_lay1[%(MAX_LAYERS)d];   // trail, soft
uniform vec3 u_base;
uniform vec3 u_head;
uniform float u_falloff;
uniform float u_gscale;
uniform sampler2D u_atlas;
uniform vec4 u_atl;                    // cols, rows, margin_x, margin_y (0..1)
uniform int u_nglyph;
out vec4 o_col;

uint pcg(uint v) {
    uint s = v * 747796405u + 2891336453u;
    uint w = ((s >> ((s >> 28u) + 4u)) ^ s) * 277803737u;
    return (w >> 22u) ^ w;
}
float h1(uint a, uint b, uint c) {
    return float(pcg(a ^ pcg(b ^ pcg(c)))) * (1.0 / 4294967296.0);
}

vec3 layer_color(int L, vec2 mp, vec2 ms, float dpi, int mi) {
    float sc = u_lay0[L].x * dpi * u_gscale;
    vec2 cell = floor(vec2(%(CELL_W)f, %(CELL_H)f) * sc + 0.5);
    float cols = floor(ms.x / cell.x);
    float rows = floor(ms.y / cell.y);
    float padx = floor((ms.x - cols * cell.x) * 0.5);
    vec2 q = vec2(mp.x - padx, mp.y);
    if (q.x < 0.0 || q.x >= cols * cell.x || q.y >= rows * cell.y) return vec3(0.0);

    vec2 cr = floor(q / cell);
    vec2 f = q / cell - cr;
    uint colu = uint(cr.x);
    uint seed = uint(L * 64 + mi * 8 + 1);

    float a = h1(colu, seed, 1u);
    float d = h1(colu, seed, 4u);
    float speed = mix(%(S0)f, %(S1)f, a) * u_lay0[L].z;
    float maxlen = %(T1)f * u_lay1[L].x;
    float gap = rows * 0.6 / u_lay0[L].w;
    float period = rows + maxlen + gap;
    float pos = u_time * speed + d * period;
    float cyc = floor(pos / period);
    float ph = pos - cyc * period;
    uint cycu = uint(max(cyc, 0.0));
    float len = mix(%(T0)f, %(T1)f, h1(colu, seed + 100u, cycu)) * u_lay1[L].x;
    float shift = gap * h1(colu, seed + 200u, cycu);
    float dist = (ph - shift) - cr.y;
    if (dist < 0.0 || dist > len) return vec3(0.0);

    float br = pow(clamp(1.0 - dist / len, 0.0, 1.0), u_falloff);
    float headness = clamp(1.0 - dist, 0.0, 1.0);

    // Glyph identity: slowly mutates in the trail, flickers fast at the head.
    uint slot = uint(u_time * 0.35 + h1(colu, uint(cr.y), seed + 300u) * 16.0);
    if (dist < 1.0) slot = uint(u_time * 12.0) + 7777u;
    uint gid = uint(h1(colu * 4099u + uint(cr.y), slot, seed + 400u) * float(u_nglyph));
    gid = min(gid, uint(u_nglyph - 1));
    uint gxu = uint(u_atl.x);
    vec2 gcell = vec2(float(gid %% gxu), float(gid / gxu));
    vec2 inner = vec2(1.0) - 2.0 * u_atl.zw;
    vec2 uv = (gcell + u_atl.zw + f * inner) / u_atl.xy;
    float blur = 1.0 + u_lay1[L].y * 5.0;
    vec2 gx = vec2(inner.x / (u_atl.x * cell.x), 0.0) * blur;
    vec2 gy = vec2(0.0, inner.y / (u_atl.y * cell.y)) * blur;
    float g = textureGrad(u_atlas, uv, gx, gy).r;
    if (u_lay1[L].y > 0.0) g *= 1.25;  // keep defocused glyphs from vanishing

    vec3 col = mix(u_base * br, u_head, headness);
    return col * g * u_lay0[L].y;
}

void main() {
    vec2 p = vec2(gl_FragCoord.x, u_res.y - gl_FragCoord.y);
    vec3 c = vec3(0.0);
    for (int m = 0; m < u_nmon; m++) {
        vec4 r = u_mon[m];
        if (p.x >= r.x && p.x < r.x + r.z && p.y >= r.y && p.y < r.y + r.w) {
            vec2 mp = p - r.xy;
            for (int L = 0; L < u_nlay; L++)
                c += layer_color(L, mp, r.zw, u_dpi[m], m);
            break;
        }
    }
    o_col = vec4(c, 1.0);
}
""" % dict(MAX_MON=MAX_MON, MAX_LAYERS=MAX_LAYERS, CELL_W=CELL_W, CELL_H=CELL_H,
           S0=SPEED_ROWS_PER_SEC[0], S1=SPEED_ROWS_PER_SEC[1],
           T0=TRAIL_LEN_ROWS[0], T1=TRAIL_LEN_ROWS[1])

DOWN_FS = """
#version 330
uniform sampler2D u_tex;
uniform vec2 u_texel;
in vec2 uv;
out vec4 o_col;
void main() {   // 4 bilinear taps = a 4x4 box average
    vec3 c = texture(u_tex, uv + u_texel * vec2(-1.0, -1.0)).rgb
           + texture(u_tex, uv + u_texel * vec2( 1.0, -1.0)).rgb
           + texture(u_tex, uv + u_texel * vec2(-1.0,  1.0)).rgb
           + texture(u_tex, uv + u_texel * vec2( 1.0,  1.0)).rgb;
    o_col = vec4(c * 0.25, 1.0);
}
"""

BLUR_FS = """
#version 330
uniform sampler2D u_tex;
uniform vec2 u_dir;   // texel step along the blur axis
in vec2 uv;
out vec4 o_col;
void main() {
    vec3 c = texture(u_tex, uv).rgb * 0.2270270;
    c += (texture(u_tex, uv + u_dir * 1.3846154).rgb
        + texture(u_tex, uv - u_dir * 1.3846154).rgb) * 0.3162162;
    c += (texture(u_tex, uv + u_dir * 3.2307692).rgb
        + texture(u_tex, uv - u_dir * 3.2307692).rgb) * 0.0702703;
    o_col = vec4(c, 1.0);
}
"""

FINAL_FS = """
#version 330
uniform sampler2D u_scene;
uniform sampler2D u_bloom1;
uniform sampler2D u_bloom2;
uniform vec2 u_res;
uniform float u_g1;
uniform float u_g2;
uniform float u_scan;
uniform float u_field;
uniform float u_vig;
uniform float u_gain;
uniform int u_nmon;
uniform vec4 u_mon[%(MAX_MON)d];
in vec2 uv;
out vec4 o_col;
void main() {
    vec3 c = texture(u_scene, uv).rgb
           + texture(u_bloom1, uv).rgb * u_g1
           + texture(u_bloom2, uv).rgb * u_g2;
    vec2 p = vec2(gl_FragCoord.x, u_res.y - gl_FragCoord.y);
    for (int m = 0; m < u_nmon; m++) {
        vec4 r = u_mon[m];
        if (p.x >= r.x && p.x < r.x + r.z && p.y >= r.y && p.y < r.y + r.w) {
            vec2 d = ((p - r.xy) / r.zw - 0.5) * 2.0;
            c *= 1.0 - u_vig * smoothstep(0.35, 1.45, length(d));
            break;
        }
    }
    c *= u_gain;
    if (u_scan > 0.0 && mod(floor(gl_FragCoord.y) + u_field, 2.0) < 1.0)
        c *= 1.0 - u_scan;
    o_col = vec4(c, 1.0);
}
""" % dict(MAX_MON=MAX_MON)

# With FSR the frame is composed at render resolution, upscaled, and only then
# gets the scanlines and flicker, so they stay one real pixel row thick.
SCAN_FS = """
#version 330
uniform sampler2D u_tex;
uniform float u_gain;
uniform float u_scan;
uniform float u_field;
uniform float u_dither;
out vec4 o_col;
float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}
void main() {
    vec3 c = texelFetch(u_tex, ivec2(gl_FragCoord.xy), 0).rgb * u_gain;
    if (u_scan > 0.0 && mod(floor(gl_FragCoord.y) + u_field, 2.0) < 1.0)
        c *= 1.0 - u_scan;
    c += (hash12(gl_FragCoord.xy) - 0.5) / 255.0 * u_dither;
    o_col = vec4(c, 1.0);
}
"""

OVERLAY_VS = """
#version 330
uniform vec4 u_rect;   // x, y, w, h in px, top-left origin
uniform vec2 u_res;
out vec2 uv;
void main() {
    vec2 corner = vec2(gl_VertexID & 1, gl_VertexID >> 1);
    uv = corner;
    vec2 px = u_rect.xy + corner * u_rect.zw;
    gl_Position = vec4(px.x / u_res.x * 2.0 - 1.0, 1.0 - px.y / u_res.y * 2.0, 0.0, 1.0);
}
"""

OVERLAY_FS = """
#version 330
uniform sampler2D u_tex;
uniform int u_use_tex;
uniform float u_reveal;   // 0..1 fraction of the width that is typed so far
uniform vec4 u_color;
in vec2 uv;
out vec4 o_col;
void main() {
    if (u_use_tex == 1) {
        if (uv.x > u_reveal) discard;
        float g = texture(u_tex, uv).r;
        o_col = vec4(u_color.rgb * g * u_color.a, 1.0);
    } else {
        o_col = u_color;
    }
}
"""


def _set(prog, name, value):
    """Set a uniform, ignoring ones the compiler optimised away."""
    try:
        prog[name].value = value
    except KeyError:
        pass


def _write(prog, name, arr):
    try:
        prog[name].write(np.ascontiguousarray(arr, dtype="f4").tobytes())
    except KeyError:
        pass


class GLRenderer:
    name = "gpu"

    def __init__(self, mons, cfg, origin, size):
        self.cfg = cfg
        self.mons = mons[:MAX_MON]
        self.size = size
        self.ctx = moderngl.create_context()
        self.ctx.disable(moderngl.DEPTH_TEST)
        vw, vh = size
        base, head = COLORS[cfg["color"]]
        self.base = tuple(c / 255 for c in base)
        self.head = tuple(c / 255 for c in head)
        self.layers = active_layers(cfg)[:MAX_LAYERS]

        # AMD FSR: render at 1/ratio of the resolution per axis, then upscale.
        # Skipped in the tiny preview window where it would only blur.
        ratio = UPSCALE_RATIO[cfg["upscaling"]] if vw >= 1000 else 1.0
        self.k = 1.0 / ratio
        self.rsize = (max(2, int(round(vw / ratio))), max(2, int(round(vh / ratio))))

        self.atlas, self.atlas_info = self._build_atlas()
        c = self.ctx
        self.fsr = FSR(c) if ratio > 1.0 else None
        self.p_scene = c.program(vertex_shader=FULLSCREEN_VS, fragment_shader=SCENE_FS)
        self.p_down = c.program(vertex_shader=FULLSCREEN_VS, fragment_shader=DOWN_FS)
        self.p_blur = c.program(vertex_shader=FULLSCREEN_VS, fragment_shader=BLUR_FS)
        self.p_final = c.program(vertex_shader=FULLSCREEN_VS, fragment_shader=FINAL_FS)
        self.p_over = c.program(vertex_shader=OVERLAY_VS, fragment_shader=OVERLAY_FS)
        self.p_scan = c.program(vertex_shader=FULLSCREEN_VS, fragment_shader=SCAN_FS)
        self.vao = {k: c.vertex_array(p, []) for k, p in
                    dict(scene=self.p_scene, down=self.p_down, blur=self.p_blur,
                         final=self.p_final, over=self.p_over, scan=self.p_scan).items()}

        def target(w, h, dtype="f1"):
            tex = c.texture((max(1, w), max(1, h)), 4, dtype=dtype)
            tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            tex.repeat_x = tex.repeat_y = False
            return tex, c.framebuffer(color_attachments=[tex])

        rw, rh = self.rsize
        self.scene_tex, self.scene_fbo = target(rw, rh)
        self.q = [target(rw // 4, rh // 4), target(rw // 4, rh // 4),
                  target(rw // 16, rh // 16), target(rw // 16, rh // 16)]
        if self.fsr:
            self.post_tex, self.post_fbo = target(rw, rh)            # composed frame, render res
            self.up_tex, self.up_fbo = target(vw, vh, "f2")          # FSR output, display res
        self._init_static_uniforms()

        self.egg = EasterEgg(cfg["easter_egg"])
        self.text_cache = {}
        self.rng = np.random.default_rng()
        self.gain = 1.0

    # ----------------------------------------------------------- setup
    def _build_atlas(self):
        custom = glyphs.custom_font_path(self.cfg["font_path"])
        latin, jp = glyphs.load_fonts(ATLAS_FONT, custom)
        pairs = glyphs.pick_glyphs(latin, jp, bool(custom))
        n = len(pairs)
        gx = 10
        gy = (n + gx - 1) // gx
        cw, ch = ATLAS_CELL
        sheet = pygame.Surface((gx * cw, gy * ch))
        for i, (g, font) in enumerate(pairs):
            sheet.blit(glyphs.render_mirrored(g, font, cw, ch),
                       ((i % gx) * cw, (i // gx) * ch))
        data = pygame.image.tobytes(sheet, "RGB")
        red = np.frombuffer(data, np.uint8).reshape(-1, 3)[:, 0].copy()
        tex = self.ctx.texture(sheet.get_size(), 1, red.tobytes())
        tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
        tex.repeat_x = tex.repeat_y = False
        tex.build_mipmaps()
        try:
            tex.anisotropy = 4.0
        except Exception:
            pass
        info = (float(gx), float(gy), ATLAS_MARGIN[0] / cw, ATLAS_MARGIN[1] / ch, n)
        return tex, info

    def _init_static_uniforms(self):
        vw, vh = self.rsize                    # everything below lives in render-resolution pixels
        k = self.k
        mons = np.zeros((MAX_MON, 4), "f4")
        dpi = np.ones(MAX_MON, "f4")
        ox = min(m["x"] for m in self.mons)
        oy = min(m["y"] for m in self.mons)
        for i, m in enumerate(self.mons):
            mons[i] = ((m["x"] - ox) * k, (m["y"] - oy) * k, m["w"] * k, m["h"] * k)
            dpi[i] = m["dpi"] * k              # glyphs keep their on-screen size after upscaling
        lay0 = np.zeros((MAX_LAYERS, 4), "f4")
        lay1 = np.zeros((MAX_LAYERS, 4), "f4")
        for i, lay in enumerate(self.layers):
            lay0[i] = (lay["scale"], lay["dim"], lay["speed"], lay["density"])
            lay1[i] = (lay["trail"], lay["soft"], 0, 0)
        gx, gy, mx, my, n = self.atlas_info
        s = self.p_scene
        _set(s, "u_res", (float(vw), float(vh)))
        _set(s, "u_nmon", len(self.mons))
        _write(s, "u_mon", mons)
        _write(s, "u_dpi", dpi)
        _set(s, "u_nlay", len(self.layers))
        _write(s, "u_lay0", lay0)
        _write(s, "u_lay1", lay1)
        _set(s, "u_base", self.base)
        _set(s, "u_head", self.head)
        _set(s, "u_falloff", float(self.cfg["trail_falloff"]))
        _set(s, "u_gscale", float(self.cfg["glyph_scale"]))
        _set(s, "u_atlas", 0)
        _set(s, "u_atl", (gx, gy, mx, my))
        _set(s, "u_nglyph", int(n))
        f = self.p_final
        _set(f, "u_res", (float(vw), float(vh)))
        _set(f, "u_nmon", len(self.mons))
        _write(f, "u_mon", mons)
        _set(f, "u_vig", float(self.cfg["vignette"]))
        _set(f, "u_scene", 0)
        _set(f, "u_bloom1", 1)
        _set(f, "u_bloom2", 2)
        bloom = float(self.cfg["bloom"])
        _set(f, "u_g1", bloom * 0.55)
        _set(f, "u_g2", bloom * 0.9)
        _set(f, "u_scan", 0.0 if self.fsr else float(self.cfg["scanlines"]))
        _set(self.p_over, "u_res", (float(vw), float(vh)))   # render resolution
        self.bloom_on = bloom > 0

    # ----------------------------------------------------------- frame
    def _fullscreen(self, key):
        self.vao[key].render(moderngl.TRIANGLES, vertices=3)

    def _blur_chain(self, src_tex, a, b):
        """src -> downsample into a -> separable blur a<->b."""
        (a_tex, a_fbo), (b_tex, b_fbo) = a, b
        w, h = a_tex.size
        a_fbo.use()
        self.ctx.viewport = (0, 0, w, h)
        src_tex.use(0)
        _set(self.p_down, "u_tex", 0)
        _set(self.p_down, "u_texel", (1.0 / src_tex.size[0], 1.0 / src_tex.size[1]))
        self._fullscreen("down")
        for src, dst, dx, dy in ((a_tex, b_fbo, 1.0 / w, 0.0), (b_tex, a_fbo, 0.0, 1.0 / h)):
            dst.use()
            src.use(0)
            _set(self.p_blur, "u_tex", 0)
            _set(self.p_blur, "u_dir", (dx, dy))
            self._fullscreen("blur")

    def render(self, t, dt, frame):
        ctx = self.ctx
        rw, rh = self.rsize
        ctx.disable(moderngl.BLEND)

        self.scene_fbo.use()
        ctx.viewport = (0, 0, rw, rh)
        self.atlas.use(0)
        _set(self.p_scene, "u_time", float(t))
        self._fullscreen("scene")
        self._draw_egg(t)

        if self.bloom_on:
            ctx.disable(moderngl.BLEND)
            self._blur_chain(self.scene_tex, self.q[0], self.q[1])
            self._blur_chain(self.q[0][0], self.q[2], self.q[3])

        if self.fsr:
            self.post_fbo.use()
        else:
            ctx.screen.use()
        ctx.viewport = (0, 0, rw, rh)
        ctx.disable(moderngl.BLEND)
        self.scene_tex.use(0)
        self.q[0][0].use(1)
        self.q[2][0].use(2)
        flick = self.cfg["flicker"]
        gain = 1.0 + flick * (float(self.rng.random()) - 0.5) * 2.0
        field = float(frame % 2) if self.cfg["interlace"] else 0.0
        _set(self.p_final, "u_gain", 1.0 if self.fsr else gain)
        _set(self.p_final, "u_field", field)
        self._fullscreen("final")

        if self.fsr:
            vw, vh = self.size
            self.fsr.upscale(self.post_tex, (rw, rh), self.up_fbo, (vw, vh),
                             sharpness=float(self.cfg["sharpness"]))
            ctx.screen.use()
            ctx.viewport = (0, 0, vw, vh)
            self.up_tex.use(0)
            s = self.p_scan
            _set(s, "u_tex", 0)
            _set(s, "u_gain", gain)
            _set(s, "u_scan", float(self.cfg["scanlines"]))
            _set(s, "u_field", field)
            _set(s, "u_dither", 1.0)
            self._fullscreen("scan")

    # ------------------------------------------------------ easter egg
    def _text_texture(self, text, height):
        key = (text, height)
        if key not in self.text_cache:
            font = glyphs.text_font(height)
            surf = font.render(text, True, (255, 255, 255), (0, 0, 0))
            data = pygame.image.tobytes(surf, "RGB")
            red = np.frombuffer(data, np.uint8).reshape(-1, 3)[:, 0].copy()
            tex = self.ctx.texture(surf.get_size(), 1, red.tobytes())
            tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self.text_cache = {key: (tex, surf.get_size())}  # keep only one
        return self.text_cache[key]

    def _draw_egg(self, t):
        state = self.egg.update(t)
        if state is None:
            return
        text, shown, alpha, cursor = state
        mon = self.mons[0]
        ox = min(m["x"] for m in self.mons)
        oy = min(m["y"] for m in self.mons)
        k = self.k
        height = max(8, int(mon["h"] * 0.05 * mon["dpi"] ** 0.5 * k))
        tex, (tw, th) = self._text_texture(text, height)
        x = (mon["x"] - ox + mon["w"] * 0.10) * k
        y = (mon["y"] - oy + mon["h"] * 0.42) * k
        ctx, p = self.ctx, self.p_over
        ctx.enable(moderngl.BLEND)

        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        pad = height * 0.6
        _set(p, "u_rect", (x - pad, y - pad * 0.6, tw + pad * 2 + height, th + pad * 1.2))
        _set(p, "u_use_tex", 0)
        _set(p, "u_color", (0.0, 0.0, 0.0, 0.88 * alpha))
        self.vao["over"].render(moderngl.TRIANGLE_STRIP, vertices=4)

        ctx.blend_func = moderngl.ONE, moderngl.ONE
        tex.use(0)
        _set(p, "u_tex", 0)
        _set(p, "u_use_tex", 1)
        _set(p, "u_rect", (x, y, float(tw), float(th)))
        _set(p, "u_reveal", shown / len(text))
        _set(p, "u_color", (*self.head, alpha))
        self.vao["over"].render(moderngl.TRIANGLE_STRIP, vertices=4)

        if cursor and alpha > 0.0:
            cw = tw / len(text)
            _set(p, "u_use_tex", 0)
            _set(p, "u_rect", (x + cw * shown, y + th * 0.12, cw * 0.8, th * 0.76))
            _set(p, "u_color", (*(c * alpha for c in self.base), 1.0))
            self.vao["over"].render(moderngl.TRIANGLE_STRIP, vertices=4)
        ctx.disable(moderngl.BLEND)

    # ------------------------------------------------------- utilities
    def screenshot(self, path):
        vw, vh = self.size
        data = self.ctx.screen.read(components=3)
        surf = pygame.image.frombuffer(data, (vw, vh), "RGB")
        pygame.image.save(pygame.transform.flip(surf, False, True), path)

    def close(self):
        pass
