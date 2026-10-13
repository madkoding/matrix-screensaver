"""Settings window shown by Windows for the screensaver's "Settings" button."""
import tkinter as tk
from tkinter import filedialog, ttk

import settings

SLIDERS = [  # (key, label, from, to, decimals)
    ("bloom", "Bloom (glow)", 0.0, 1.0, 2),
    ("scanlines", "Scanlines", 0.0, 0.9, 2),
    ("vignette", "Vignette", 0.0, 1.0, 2),
    ("flicker", "Flicker", 0.0, 0.2, 2),
    ("speed", "Fall speed", 0.4, 2.5, 2),
    ("density", "Rain density", 0.3, 1.6, 2),
    ("glyph_scale", "Glyph size", 0.6, 2.0, 2),
    ("trail_falloff", "Trail fade (higher = shorter)", 0.6, 4.0, 2),
    ("sharpness", "FSR sharpening (0 = sharpest)", 0.0, 2.0, 2),
]
CHECKS = [
    ("interlace", "Animated interlacing (alternate scanline fields)"),
    ("depth", "Depth layers (parallax)"),
    ("easter_egg", 'Occasional typed messages ("Wake up, Neo...")'),
]


def show():
    cfg = settings.load()
    root = tk.Tk()
    root.title("Matrix Screensaver Settings")
    root.resizable(False, False)
    frm = ttk.Frame(root, padding=14)
    frm.grid()

    vars_ = {}
    row = 0

    ttk.Label(frm, text="Color").grid(row=row, column=0, sticky="w", pady=3)
    vars_["color"] = tk.StringVar(value=cfg["color"])
    ttk.Combobox(frm, textvariable=vars_["color"], values=list(settings.COLORS),
                 state="readonly", width=14).grid(row=row, column=1, sticky="w", padx=8)
    row += 1

    for key, label, lo, hi, dec in SLIDERS:
        ttk.Label(frm, text=label).grid(row=row, column=0, sticky="w", pady=3)
        var = tk.DoubleVar(value=cfg[key])
        vars_[key] = var
        ttk.Scale(frm, from_=lo, to=hi, variable=var, length=220).grid(
            row=row, column=1, padx=8)
        val = ttk.Label(frm, width=5)
        val.grid(row=row, column=2, sticky="e")

        def refresh(*_a, var=var, val=val, dec=dec):
            val.config(text=f"{var.get():.{dec}f}")
        var.trace_add("write", refresh)
        refresh()
        row += 1

    for key, label in CHECKS:
        vars_[key] = tk.BooleanVar(value=cfg[key])
        ttk.Checkbutton(frm, text=label, variable=vars_[key]).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=2)
        row += 1

    ttk.Label(frm, text="Renderer").grid(row=row, column=0, sticky="w", pady=3)
    vars_["renderer"] = tk.StringVar(value=cfg["renderer"])
    ttk.Combobox(frm, textvariable=vars_["renderer"], values=["auto", "gpu", "software"],
                 state="readonly", width=14).grid(row=row, column=1, sticky="w", padx=8)
    row += 1

    ttk.Label(frm, text="Upscaling (AMD FSR 1.0)").grid(row=row, column=0, sticky="w", pady=3)
    vars_["upscaling"] = tk.StringVar(value=cfg["upscaling"])
    ttk.Combobox(frm, textvariable=vars_["upscaling"], values=list(settings.UPSCALE_RATIO),
                 state="readonly", width=14).grid(row=row, column=1, sticky="w", padx=8)
    row += 1

    ttk.Label(frm, text="Custom font (optional)").grid(row=row, column=0, sticky="w", pady=3)
    vars_["font_path"] = tk.StringVar(value=cfg["font_path"])
    ttk.Entry(frm, textvariable=vars_["font_path"], width=30).grid(
        row=row, column=1, padx=8, sticky="w")

    def browse():
        path = filedialog.askopenfilename(
            filetypes=[("Fonts", "*.ttf *.otf"), ("All files", "*.*")])
        if path:
            vars_["font_path"].set(path)
    ttk.Button(frm, text="Browse...", command=browse).grid(row=row, column=2)
    row += 1

    def reset():
        for k, v in settings.DEFAULTS.items():
            vars_[k].set(v)

    def ok():
        out = {k: v.get() for k, v in vars_.items()}
        settings.save(out)
        # Round-trip through load() so out-of-range values are clamped.
        settings.save(settings.load())
        root.destroy()

    btns = ttk.Frame(frm)
    btns.grid(row=row, column=0, columnspan=3, sticky="e", pady=(12, 0))
    ttk.Button(btns, text="Reset to defaults", command=reset).pack(side="left", padx=4)
    ttk.Button(btns, text="OK", command=ok).pack(side="left", padx=4)
    ttk.Button(btns, text="Cancel", command=root.destroy).pack(side="left", padx=4)
    root.mainloop()
