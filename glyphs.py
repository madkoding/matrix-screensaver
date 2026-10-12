"""Glyph set and font loading shared by both renderers."""
import glob
import os
import sys

# Half-width katakana + a few digits/symbols, all mirrored like the movie.
GLYPHS = (
    [chr(c) for c in range(0xFF66, 0xFF9E)]
    + list("0123456789")
    + list(':.="*+-<>|')
)
LATIN_FONT = r"C:\Windows\Fonts\courbd.ttf"  # Courier New Bold
JP_FONTS = [
    r"C:\Windows\Fonts\msgothic.ttc",
    r"C:\Windows\Fonts\YuGothM.ttc",
    r"C:\Windows\Fonts\meiryo.ttc",
]


def _app_dir():
    return os.path.dirname(sys.executable if getattr(sys, "frozen", False)
                           else os.path.abspath(__file__))


def custom_font_path(configured=""):
    """A user-supplied font: the `font_path` setting, else the first
    .ttf/.otf found in a `fonts` folder next to the program."""
    if configured and os.path.exists(configured):
        return configured
    found = sorted(glob.glob(os.path.join(_app_dir(), "fonts", "*.[to]tf")))
    return found[0] if found else ""


def load_fonts(size, custom=""):
    """(latin_font, japanese_font): Courier New Bold + a CJK fallback, or the
    custom font for everything."""
    import pygame
    if custom:
        font = pygame.font.Font(custom, size)
        return font, font
    if os.path.exists(LATIN_FONT):
        latin = pygame.font.Font(LATIN_FONT, size)
    else:
        latin = pygame.font.SysFont("couriernew", size, bold=True)
    jp = None
    for path in JP_FONTS:
        if os.path.exists(path):
            jp = pygame.font.Font(path, size)
            break
    if jp is None:
        jp = pygame.font.SysFont("msgothic,yugothic,meiryo", size)
    jp.set_bold(True)  # MS Gothic has no bold face; SDL synthesises it
    return latin, jp


def pick_glyphs(latin, jp, custom=False):
    """[(glyph, font)] for every glyph a font can draw.

    Courier New draws a "tofu" box for katakana instead of reporting the glyph
    missing, so route by Unicode range, not by metrics().
    """
    pairs = []
    for g in GLYPHS:
        f = latin if (custom or ord(g) < 0x3000) else jp
        m = f.metrics(g)
        if m and m[0]:
            pairs.append((g, f))
    return pairs


def render_mirrored(g, font, w, h):
    """White-on-black w x h surface with the glyph centred and mirrored."""
    import pygame
    raw = pygame.transform.flip(font.render(g, True, (255, 255, 255)), True, False)
    cell = pygame.Surface((w, h))
    cell.blit(raw, raw.get_rect(center=(w // 2, h // 2)))
    return cell


def text_font(size):
    """Courier New Bold at `size` px, for the typed on-screen messages."""
    import pygame
    if os.path.exists(LATIN_FONT):
        return pygame.font.Font(LATIN_FONT, size)
    return pygame.font.SysFont("couriernew", size, bold=True)
