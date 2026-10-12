# Matrix Screensaver

Lluvia de código de *The Matrix* como protector de pantalla para Windows, escrito en Python y con soporte multimonitor.

![Tres monitores](docs/screenshot.png)

*Captura real en un setup de 3 monitores (un ultrawide central y dos verticales).*

![Detalle](docs/detail.png)

## Características

- **Multimonitor:** cada pantalla tiene su propia lluvia, ajustada a su resolución y posición (también con monitores de tamaños y orientaciones distintos).
- **Glifos de la película:** katakana de ancho medio espejado (MS Gothic) más dígitos y símbolos en Courier New Bold.
- **Cabeza brillante y estela:** el glifo líder es casi blanco, la estela se apaga en verde fosforescente y los glifos mutan al azar.
- **Profundidad:** tres capas con paralaje (lejana tenue y lenta, media, y cercana grande y desenfocada).
- **Bloom** sutil alrededor de las columnas brillantes.
- **Efecto CRT:** scanlines con interlazado animado (alternan los campos par/impar en cada fotograma).
- Sale con cualquier tecla, clic o movimiento del ratón.

## Instalación

### Opción 1: compilar el `.scr`

Requiere Windows y Python 3.10+.

```powershell
python -m pip install pygame-ce numpy pyinstaller
.\build.ps1
```

Esto genera `MatrixRain.scr`. Haz clic derecho sobre él → **Instalar** y Windows abrirá el selector de protectores de pantalla con este ya elegido.

### Opción 2: ejecutar desde Python

```powershell
python -m pip install pygame-ce numpy
python matrix_saver.py /s
```

Para una prueba automática de N segundos con captura al terminar:

```powershell
python matrix_saver.py /s --seconds 8 --shot captura.png
```

## Configuración

Los parámetros están al inicio de [`matrix_saver.py`](matrix_saver.py):

| Constante | Qué hace |
|---|---|
| `BLOOM_GAIN` | Intensidad del bloom (0 lo desactiva). |
| `SCANLINE_STRENGTH` | Oscuridad de las scanlines (0 las desactiva). |
| `INTERLACE_FRAMES` | Fotogramas que dura cada campo del interlazado. |
| `LAYERS` | Tamaño, brillo, velocidad, densidad, estela y desenfoque de cada capa de profundidad. |
| `trail_brightness()` | Curva con la que se apaga la estela detrás de cada cabeza. |
| `BASE_COLOR` / `HEAD_COLOR` | Colores de la estela y de la cabeza. |

## Cómo funciona

- Un `.scr` es un `.exe` renombrado; Windows lo lanza con `/s` (ejecutar), `/c` (configurar) o `/p` (vista previa, aquí en blanco). [PyInstaller](https://pyinstaller.org) empaqueta el script.
- Una sola ventana sin bordes cubre el escritorio virtual completo y cada monitor se dibuja con su propia cuadrícula. Se activa DPI-awareness por monitor para que las coordenadas sean píxeles reales.
- Cada glifo se pre-renderiza una vez en 20 niveles de brillo, y los fotogramas solo copian superficies con `BLEND_ADD`, de modo que los halos de celdas vecinas se suman.
- El bloom se calcula desde la cuadrícula de brillo (un píxel por celda), se difumina con numpy y se compone a 1/4 de resolución antes de sumarse a la pantalla.
- El rendimiento ronda los 45 FPS en tres monitores (7,8 millones de píxeles).

## Requisitos

- Windows 10/11
- Fuentes `msgothic.ttc` y `courbd.ttf` (vienen con Windows)
- Python 3.10+, `pygame-ce`, `numpy`
