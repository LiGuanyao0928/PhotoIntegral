"""读取 Mac「照片」App 的图库（需要 macOS + `pip install osxphotos`）。

开启 iCloud 照片后，iPhone 上的照片会同步到 Mac 图库；
在 Mac 上建的相簿也会同步回 iPhone，这是整理手机相册最稳的办法。
"""

from __future__ import annotations

from pathlib import Path

from ..models import Photo


def _attr(obj, name, default=None):
    try:
        value = getattr(obj, name)
    except Exception:
        return default
    return default if value is None else value


class MacPhotosSource:
    def __init__(self, library=None):
        try:
            import osxphotos
        except ImportError as e:
            raise SystemExit("读取照片图库需要 macOS 并安装 osxphotos：pip install 'photointegral[macos]'") from e
        self.db = osxphotos.PhotosDB(dbfile=library) if library else osxphotos.PhotosDB()

    def photos(self) -> list[Photo]:
        return [self._convert(p) for p in self.db.photos(intrash=False)]

    @staticmethod
    def _convert(p) -> Photo:
        lat, lon = _attr(p, "location", (None, None))
        place = _attr(p, "place")
        country = city = None
        if place is not None:
            address = _attr(place, "address")
            country = _attr(address, "country") if address else None
            city = _attr(address, "city") if address else None
            if not city:
                names = _attr(place, "names")
                cities = _attr(names, "city", []) if names else []
                city = cities[0] if cities else None
        exif = _attr(p, "exif_info")
        date = _attr(p, "date")
        # 原图可能只在 iCloud 里没下载到本地，这时 path 为空，「相似照片」会跳过它
        path = _attr(p, "path")
        if date is not None and date.tzinfo is not None:
            date = date.replace(tzinfo=None)
        return Photo(
            id=p.uuid,
            filename=_attr(p, "original_filename", p.uuid),
            path=Path(path) if path else None,
            date=date,
            size=_attr(p, "original_filesize", 0),
            width=_attr(p, "width", 0),
            height=_attr(p, "height", 0),
            latitude=lat,
            longitude=lon,
            country=country,
            city=city,
            camera_make=_attr(exif, "camera_make") if exif else None,
            camera_model=_attr(exif, "camera_model") if exif else None,
            lens_model=_attr(exif, "lens_model") if exif else None,
            is_video=bool(_attr(p, "ismovie", False)),
            is_screenshot=bool(_attr(p, "screenshot", False)),
            is_selfie=bool(_attr(p, "selfie", False)),
            is_live=bool(_attr(p, "live_photo", False)),
            is_burst=bool(_attr(p, "burst", False)),
            is_portrait=bool(_attr(p, "portrait", False)),
            is_panorama=bool(_attr(p, "panorama", False)),
            is_favorite=bool(_attr(p, "favorite", False)),
            is_hidden=bool(_attr(p, "hidden", False)),
            duration=float(_attr(p, "duration", 0) or 0),
            persons=[x for x in _attr(p, "persons", []) if x and x != "_UNKNOWN_"],
            labels=list(_attr(p, "labels", [])),
            keywords=list(_attr(p, "keywords", [])),
            albums=list(_attr(p, "albums", [])),
            fingerprint=_attr(p, "fingerprint"),
        )
