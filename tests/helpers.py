from datetime import datetime
from pathlib import Path

from PIL import Image


def make_jpeg(path: Path, when: datetime, color=(200, 50, 50), model="iPhone 15 Pro", gps=None, lens=None, pattern=0):
    img = Image.new("RGB", (64, 48), color)
    # 画些条纹让感知哈希有内容
    for x in range(0, 64, 8):
        for y in range(48):
            img.putpixel(((x + pattern) % 64, y), (255 - color[0], 255 - color[1], 255 - color[2]))
    exif = Image.Exif()
    exif[0x010F] = "Apple"
    exif[0x0110] = model
    sub = exif.get_ifd(0x8769)
    sub[0x9003] = when.strftime("%Y:%m:%d %H:%M:%S")
    if lens:
        sub[0xA434] = lens
    if gps:
        lat, lon = gps
        g = exif.get_ifd(0x8825)
        g[1] = "N" if lat >= 0 else "S"
        g[2] = _dms(abs(lat))
        g[3] = "E" if lon >= 0 else "W"
        g[4] = _dms(abs(lon))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", exif=exif)
    return path


def _dms(deg):
    d = int(deg)
    m = int((deg - d) * 60)
    s = round(((deg - d) * 60 - m) * 60, 2)
    return (float(d), float(m), float(s))


def make_png(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (30, 60), (10, 10, 10)).save(path, "PNG")
    return path
