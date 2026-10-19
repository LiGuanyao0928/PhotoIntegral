"""照片的统一数据模型，各个来源都转换成这个结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".avi", ".3gp"}
IMAGE_EXTS = {".jpg", ".jpeg", ".heic", ".heif", ".png", ".gif", ".tif", ".tiff", ".dng", ".webp"}


@dataclass
class Photo:
    id: str
    filename: str
    path: Optional[Path] = None
    date: Optional[datetime] = None
    size: int = 0
    width: int = 0
    height: int = 0
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    country: Optional[str] = None
    city: Optional[str] = None
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    lens_model: Optional[str] = None
    is_video: bool = False
    is_screenshot: bool = False
    is_selfie: bool = False
    is_live: bool = False
    is_burst: bool = False
    is_portrait: bool = False
    is_panorama: bool = False
    is_favorite: bool = False
    is_hidden: bool = False
    duration: float = 0.0
    persons: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    albums: list[str] = field(default_factory=list)
    # 用于精确去重的内容指纹（文件哈希或照片 App 的 fingerprint）
    fingerprint: Optional[str] = None

    @property
    def extension(self) -> str:
        return Path(self.filename).suffix.lower()

    @property
    def size_mb(self) -> float:
        return self.size / (1024 * 1024)

    @property
    def megapixels(self) -> float:
        return self.width * self.height / 1_000_000

    @property
    def orientation(self) -> str:
        if not self.width or not self.height:
            return "unknown"
        if self.width > self.height:
            return "landscape"
        if self.width < self.height:
            return "portrait"
        return "square"

    @property
    def has_location(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def media_type(self) -> str:
        if self.is_video:
            return "video"
        if self.is_screenshot:
            return "screenshot"
        return "photo"

    def get(self, name: str):
        """按字段名取值，供自定义规则使用（支持属性）。"""
        if name == "year":
            return self.date.year if self.date else None
        if name == "month":
            return self.date.month if self.date else None
        if name == "weekday":
            return self.date.isoweekday() if self.date else None
        if name == "hour":
            return self.date.hour if self.date else None
        if not hasattr(self, name):
            raise KeyError(f"未知字段: {name}")
        return getattr(self, name)
