"""把照片按相簿归档到文件夹：dest/相簿/子相簿/文件名。

mode:
  copy     复制（默认，最安全，占双倍空间）
  link     硬链接（不占额外空间，要求同一个磁盘）
  symlink  符号链接
  move     移动：先放进所有相簿，全部成功后再删除原文件
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from ..plan import Plan

MODES = ("copy", "link", "symlink", "move")
_UNSAFE = str.maketrans({c: "_" for c in '<>:"\\|?*'})


def _safe_parts(album: str) -> list[str]:
    return [p.translate(_UNSAFE).strip(" .") or "_" for p in album.split("/") if p.strip()]


def _unique(target: Path) -> Path:
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    i = 1
    while True:
        candidate = target.with_name(f"{stem} ({i}){suffix}")
        if not candidate.exists():
            return candidate
        i += 1


class FolderSink:
    def __init__(self, dest, mode: str = "copy"):
        if mode not in MODES:
            raise ValueError(f"mode 只能是 {', '.join(MODES)}")
        self.dest = Path(dest).expanduser()
        self.mode = mode

    def apply(self, plan: Plan, dry_run: bool = False, log=print) -> dict:
        if plan.source.get("kind") != "folder":
            raise SystemExit("输出到文件夹需要文件夹来源（Mac 图库请用 --sink macos，或先用照片 App 导出）")
        placed, used = 0, set()
        for album, ids in plan.albums.items():
            folder = self.dest.joinpath(*_safe_parts(album))
            for pid in ids:
                src = Path(plan.files[pid])
                if not src.exists():
                    log(f"  跳过（文件不存在）: {src}")
                    continue
                target = folder / src.name
                if dry_run:
                    log(f"  [{self.mode}] {src} -> {target}")
                else:
                    folder.mkdir(parents=True, exist_ok=True)
                    if target.exists() and target.stat().st_size == src.stat().st_size:
                        used.add(src)  # 已经归档过，重复执行不会再复制一份
                        continue
                    self._place(src, _unique(target))
                used.add(src)
                placed += 1
        removed = 0
        if self.mode == "move" and not dry_run:
            for src in used:
                if src.exists() and not self._inside_dest(src):
                    src.unlink()
                    removed += 1
        return {"placed": placed, "removed": removed}

    def _inside_dest(self, p: Path) -> bool:
        try:
            p.resolve().relative_to(self.dest.resolve())
            return True
        except ValueError:
            return False

    def _place(self, src: Path, target: Path) -> None:
        if self.mode in ("copy", "move"):
            shutil.copy2(src, target)
        elif self.mode == "link":
            os.link(src, target)
        else:
            target.symlink_to(src.resolve())
