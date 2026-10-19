"""把方案的分组结果合成一份「整理计划」，可以先预览、保存，确认后再执行。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .models import Photo
from .strategies import Strategy


@dataclass
class Plan:
    source: dict
    albums: dict[str, list[str]] = field(default_factory=dict)  # 相簿 -> 照片 id
    files: dict[str, str] = field(default_factory=dict)  # 照片 id -> 文件路径（文件夹来源）

    @classmethod
    def build(cls, photos: list[Photo], strategies: list[Strategy], source: dict) -> "Plan":
        plan = cls(source=source)
        for strategy in strategies:
            for album, items in strategy.run(photos).items():
                ids = plan.albums.setdefault(album, [])
                seen = set(ids)
                for p in items:
                    if p.id not in seen:
                        ids.append(p.id)
                        seen.add(p.id)
                    if p.path:
                        plan.files[p.id] = str(p.path)
        plan.albums = dict(sorted(plan.albums.items()))
        return plan

    def summary(self, max_albums: int = 200) -> str:
        if not self.albums:
            return "没有照片符合所选方案。"
        lines = []
        total = len({pid for ids in self.albums.values() for pid in ids})
        lines.append(f"共 {len(self.albums)} 个相簿，涉及 {total} 个文件：")
        width = min(max(len(a) for a in self.albums), 60)
        for i, (album, ids) in enumerate(self.albums.items()):
            if i >= max_albums:
                lines.append(f"  ……还有 {len(self.albums) - max_albums} 个相簿")
                break
            lines.append(f"  {album:<{width}}  {len(ids):>6}")
        return "\n".join(lines)

    def save(self, path) -> None:
        data = {"version": 1, "source": self.source, "albums": self.albums, "files": self.files}
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path) -> "Plan":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(source=data["source"], albums=data["albums"], files=data.get("files", {}))
