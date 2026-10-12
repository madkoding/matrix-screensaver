"""Generates icon.ico (a green mirrored katakana on black). Dev-only: needs Pillow."""
from PIL import Image, ImageDraw, ImageFont

SIZE = 256
img = Image.new("RGB", (SIZE, SIZE), (0, 8, 2))
draw = ImageDraw.Draw(img)
font = ImageFont.truetype(r"C:\Windows\Fonts\msgothic.ttc", 190)
glyph = Image.new("L", (SIZE, SIZE), 0)
ImageDraw.Draw(glyph).text((SIZE // 2, SIZE // 2), "ｦ", font=font, fill=255, anchor="mm")
glyph = glyph.transpose(Image.FLIP_LEFT_RIGHT)
img.paste((0, 255, 70), mask=glyph)
img.save("icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
