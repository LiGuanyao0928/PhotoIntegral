"""扫描一个文件夹（例如用数据线从 iPhone 导出的 DCIM），读取 EXIF。

适用于 Windows / Linux，或者不想动 Mac 照片图库的情况。
EXIF 读取依赖 Pillow；HEIC 需要额外安装 pillow-heif。
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from ..models import IMAGE_EXTS, VIDEO_EXTS, Photo

try:
    from PIL import Image, ExifTags
except ImportError:  # pragma: no cover - Pillow 是可选依赖
    Image = None
    ExifTags = None

try:  # pragma: no cover
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass

_SCREENSHOT_NAME = re.compile(r"(screenshot|screen shot|屏幕快照|截屏|截图)", re.IGNORECASE)
_BURST_NAME = re.compile(r"_BURST\d+", re.IGNORECASE)
_DATE_IN_NAME = re.compile(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})[-_ ]?(\d{2})?(\d{2})?(\d{2})?")

GPS_IFD = 0x8825
EXIF_IFD = 0x8769


def _rational(value) -> float:
    try:
        return float(value)
    except TypeError:
        num, den = value
        return num / den if den else 0.0


def _gps_to_degrees(coord, ref) -> Optional[float]:
    if not coord:
        return None
    d, m, s = (_rational(x) for x in coord)
    deg = d + m / 60 + s / 3600
    if ref in ("S", "W"):
        deg = -deg
    return deg


def _parse_exif_date(value: str) -> Optional[datetime]:
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value.strip("\x00 "), fmt)
        except (ValueError, AttributeError):
            continue
    return None


def _date_from_name(name: str) -> Optional[datetime]:
    m = _DATE_IN_NAME.search(name)
    if not m:
        return None
    parts = [int(p) if p else 0 for p in m.groups()]
    try:
        return datetime(*parts)
    except ValueError:
        return None


def file_hash(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


class FolderSource:
    def __init__(self, path, hash_files: bool = True):
        self.root = Path(path).expanduser()
        self.hash_files = hash_files
        if not self.root.is_dir():
            raise FileNotFoundError(f"文件夹不存在: {self.root}")

    def iter_files(self) -> Iterator[Path]:
        for p in sorted(self.root.rglob("*")):
            if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in IMAGE_EXTS | VIDEO_EXTS:
                yield p

    def photos(self) -> list[Photo]:
        files = list(self.iter_files())
        result = [self._load(p) for p in files]
        self._mark_live_photos(result)
        return result

    def _load(self, path: Path) -> Photo:
        stat = path.stat()
        ext = path.suffix.lower()
        photo = Photo(
            id=str(path.relative_to(self.root)),
            filename=path.name,
            path=path,
            size=stat.st_size,
            is_video=ext in VIDEO_EXTS,
            is_burst=bool(_BURST_NAME.search(path.name)),
        )
        if not photo.is_video:
            self._read_exif(photo)
        if photo.date is None:
            photo.date = _date_from_name(path.name) or datetime.fromtimestamp(stat.st_mtime)
        # iPhone 截图：PNG 且没有相机信息，或者文件名里带「截图」
        if not photo.is_video and (
            _SCREENSHOT_NAME.search(path.name) or (ext == ".png" and not photo.camera_model)
        ):
            photo.is_screenshot = True
        if self.hash_files:
            photo.fingerprint = file_hash(path)
        return photo

    def _read_exif(self, photo: Photo) -> None:
        if Image is None:
            return
        try:
            with Image.open(photo.path) as img:
                photo.width, photo.height = img.size
                exif = img.getexif()
        except Exception:
            return
        if not exif:
            return
        tags = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
        try:
            sub = exif.get_ifd(EXIF_IFD)
            tags.update({ExifTags.TAGS.get(k, k): v for k, v in sub.items()})
        except Exception:
            pass
        photo.camera_make = (tags.get("Make") or None) and str(tags["Make"]).strip("\x00 ")
        photo.camera_model = (tags.get("Model") or None) and str(tags["Model"]).strip("\x00 ")
        lens = tags.get("LensModel")
        if lens:
            photo.lens_model = str(lens).strip("\x00 ")
            photo.is_selfie = "front" in photo.lens_model.lower()
        date = tags.get("DateTimeOriginal") or tags.get("DateTime")
        if date:
            photo.date = _parse_exif_date(str(date))
        try:
            gps = exif.get_ifd(GPS_IFD)
        except Exception:
            gps = None
        if gps:
            lat = _gps_to_degrees(gps.get(2), gps.get(1))
            lon = _gps_to_degrees(gps.get(4), gps.get(3))
            if lat is not None and lon is not None:
                photo.latitude, photo.longitude = lat, lon

    @staticmethod
    def _mark_live_photos(photos: list[Photo]) -> None:
        """同名的 HEIC/JPG + MOV 是一张实况照片（Live Photo）。"""
        by_stem: dict[tuple[str, str], list[Photo]] = {}
        for p in photos:
            key = (str(p.path.parent), p.path.stem.lower())
            by_stem.setdefault(key, []).append(p)
        for group in by_stem.values():
            if any(p.is_video for p in group) and any(not p.is_video for p in group):
                for p in group:
                    p.is_live = True
