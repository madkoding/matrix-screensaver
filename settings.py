"""User settings (JSON in %APPDATA%) and the look-and-feel constants shared by
both renderers."""
import json
import os

# ---------------------------------------------------------------- constants
CELL_W, CELL_H = 20, 28   # grid cell in px at scale 1.0 (glyph centred inside)
FONT_SIZE = 26            # px at scale 1.0
SPEED_ROWS_PER_SEC = (9.0, 28.0)
TRAIL_LEN_ROWS = (10.0, 38.0)

# Depth: three parallax layers drawn far -> near and added together.
#   scale   glyph/cell size vs. the middle layer
#   dim     brightness of the layer (distance haze)
#   speed   fall-speed multiplier (rows/s; pixels/s also grows with scale)
#   density fraction of columns that rain at once
#   trail   trail-length multiplier
#   soft    0..1 defocus (the near layer is out of focus)
LAYERS = [
    dict(scale=0.65, dim=0.40, speed=0.9, density=0.6, trail=1.2, soft=0.0),
    dict(scale=1.00, dim=1.00, speed=1.0, density=0.7, trail=1.0, soft=0.0),
    dict(scale=1.80, dim=1.00, speed=0.9, density=0.12, trail=0.5, soft=0.55),
]

# name -> (trail color, head color)
COLORS = {
    "film": ((0, 255, 70), (205, 255, 220)),
    "classic": ((0, 255, 0), (210, 255, 210)),
    "amber": ((255, 176, 0), (255, 235, 190)),
    "red": ((255, 40, 30), (255, 215, 205)),
    "blue": ((40, 150, 255), (210, 235, 255)),
    "white": ((215, 225, 255), (255, 255, 255)),
}

# The film has Neo's screen messages; they type out over the rain now and then.
PHRASES = [
    "Wake up, Neo...",
    "The Matrix has you...",
    "Follow the white rabbit.",
    "Knock, knock, Neo.",
]

# AMD FSR 1.0 upscaling: name -> how many times fewer pixels per axis are rendered
UPSCALE_RATIO = {"off": 1.0, "quality": 1.5, "balanced": 1.7, "performance": 2.0}

# ----------------------------------------------------------------- settings
DEFAULTS = {
    "color": "film",
    "bloom": 0.5,           # 0..1 glow strength
    "scanlines": 0.45,      # 0..0.9 darkness of the scanlines
    "interlace": True,      # alternate even/odd scanline fields every frame
    "vignette": 0.35,       # 0..1 darkening toward the monitor corners
    "flicker": 0.03,        # 0..0.2 subtle global brightness jitter
    "speed": 1.0,           # 0.4..2.5 fall speed multiplier
    "density": 1.0,         # 0.3..1.6 how many columns rain at once
    "glyph_scale": 1.0,     # 0.6..2.0 glyph size multiplier
    "trail_falloff": 1.6,   # 0.6..4 trail fade curve (higher = shorter glow)
    "depth": True,          # three parallax layers instead of one
    "easter_egg": True,     # occasional typed "Wake up, Neo..." messages
    "renderer": "auto",     # auto | gpu | software
    "font_path": "",        # optional TTF/OTF replacing the glyph font
    "upscaling": "off",     # off | quality (1.5x) | balanced (1.7x) | performance (2x), AMD FSR 1.0
    "sharpness": 0.2,       # 0..2 FSR sharpening in stops (0 = sharpest, AMD default 0.2)
}
RANGES = {
    "bloom": (0.0, 1.0), "scanlines": (0.0, 0.9), "vignette": (0.0, 1.0),
    "flicker": (0.0, 0.2), "speed": (0.4, 2.5), "density": (0.3, 1.6),
    "glyph_scale": (0.6, 2.0), "trail_falloff": (0.6, 4.0), "sharpness": (0.0, 2.0),
}


def settings_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "MatrixRain", "settings.json")


def load():
    """Defaults overlaid with whatever valid values the JSON file contains."""
    cfg = dict(DEFAULTS)
    try:
        with open(settings_path(), encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return cfg
    if not isinstance(raw, dict):
        return cfg
    for key, default in DEFAULTS.items():
        if key not in raw:
            continue
        val = raw[key]
        if isinstance(default, bool):
            if isinstance(val, bool):
                cfg[key] = val
        elif isinstance(default, (int, float)):
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                lo, hi = RANGES[key]
                cfg[key] = min(hi, max(lo, float(val)))
        elif key == "color":
            if val in COLORS:
                cfg[key] = val
        elif key == "renderer":
            if val in ("auto", "gpu", "software"):
                cfg[key] = val
        elif key == "upscaling":
            if val in UPSCALE_RATIO:
                cfg[key] = val
        elif isinstance(val, str):
            cfg[key] = val
    return cfg


def save(cfg):
    path = settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)


def active_layers(cfg):
    """LAYERS adjusted by the user's speed/density; one layer if depth is off."""
    layers = LAYERS if cfg["depth"] else [LAYERS[1]]
    out = []
    for lay in layers:
        lay = dict(lay)
        lay["speed"] *= cfg["speed"]
        lay["density"] = min(1.0, lay["density"] * cfg["density"])
        out.append(lay)
    return out
