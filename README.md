# Matrix Screensaver

The digital rain from *The Matrix* as a Windows screensaver, written in Python with multi-monitor support.

![Three monitors](docs/screenshot.png)

*Real capture from a 3-monitor setup (a central ultrawide plus two portrait displays).*

![Detail](docs/detail.png)

## Features

- **Multi-monitor:** every display runs its own rain, fitted to its resolution and position (mixed sizes and orientations work).
- **Film glyphs:** mirrored half-width katakana (MS Gothic) plus digits and symbols in Courier New Bold.
- **Bright head and trail:** the leading glyph is almost white, the trail fades through phosphor green, and glyphs randomly mutate.
- **Depth:** three parallax layers (a dim, slow far layer, a middle layer, and a large out-of-focus near layer).
- **Subtle bloom** around bright columns.
- **CRT look:** scanlines with animated interlacing (even/odd fields alternate every frame).
- Exits on any key press, click, or mouse movement.

## Download

Grab `MatrixRain.scr` from the [latest release](../../releases/latest), then right-click it and choose **Install**. Windows opens the screensaver picker with it already selected.

## Build from source

Requires Windows and Python 3.10+.

```powershell
python -m pip install pygame-ce numpy pyinstaller
.\build.ps1
```

This produces `MatrixRain.scr`.

### Run directly from Python

```powershell
python -m pip install pygame-ce numpy
python matrix_saver.py /s
```

For an automatic N-second test run that saves a screenshot at the end:

```powershell
python matrix_saver.py /s --seconds 8 --shot capture.png
```

## Configuration

All settings live at the top of [`matrix_saver.py`](matrix_saver.py):

| Constant | What it does |
|---|---|
| `BLOOM_GAIN` | Bloom strength (0 disables it). |
| `SCANLINE_STRENGTH` | How dark the scanlines are (0 disables them). |
| `INTERLACE_FRAMES` | Frames each interlace field stays on. |
| `LAYERS` | Size, brightness, speed, density, trail length and blur of each depth layer. |
| `trail_brightness()` | Curve controlling how a trail fades behind each head. |
| `BASE_COLOR` / `HEAD_COLOR` | Trail and head colors. |

## How it works

- A `.scr` is just a renamed `.exe`; Windows launches it with `/s` (run), `/c` (configure) or `/p` (preview, left blank here). [PyInstaller](https://pyinstaller.org) packages the script.
- A single borderless window covers the whole virtual desktop and each monitor is drawn on its own grid. Per-monitor DPI awareness is enabled so coordinates are real pixels.
- Each glyph is pre-rendered once at 20 brightness levels, and frames only copy surfaces with `BLEND_ADD`, so halos of neighboring cells add up.
- Bloom is computed from the brightness grid (one pixel per cell), blurred with numpy, and composed at 1/4 resolution before being added to the screen.
- Performance is around 45 FPS across three monitors (7.8 million pixels).

## Requirements

- Windows 10/11
- Fonts `msgothic.ttc` and `courbd.ttf` (shipped with Windows)
- Python 3.10+, `pygame-ce`, `numpy`
