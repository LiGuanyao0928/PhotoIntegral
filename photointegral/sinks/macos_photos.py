"""在 Mac「照片」App 里创建相簿并把照片加进去（需要 `pip install photoscript`）。

开启 iCloud 照片后，这些相簿会自动同步到 iPhone 的「相簿」页。
只会新建相簿、往相簿里加照片，绝不会删除照片：相簿只是引用，
删掉相簿不会删照片。「待清理」里的照片请自己在 iPhone 上确认后再删。
"""

from __future__ import annotations

from ..plan import Plan

BATCH = 200


class MacPhotosSink:
    def __init__(self, root_folder: str | None = "PhotoIntegral"):
        try:
            import photoscript
        except ImportError as e:
            raise SystemExit("写入照片图库需要 macOS 并安装 photoscript：pip install 'photointegral[macos]'") from e
        self.ps = photoscript
        self.lib = photoscript.PhotosLibrary()
        self.root_folder = root_folder

    def apply(self, plan: Plan, dry_run: bool = False, log=print) -> dict:
        if plan.source.get("kind") != "macos":
            raise SystemExit("写入照片图库需要 Mac 图库来源（--source macos）")
        added = 0
        for album_path, ids in plan.albums.items():
            parts = [p for p in album_path.split("/") if p]
            if self.root_folder:
                parts = [self.root_folder, *parts]
            log(f"  {'/'.join(parts)}  ({len(ids)})")
            if dry_run:
                continue
            album = self._ensure_album(parts[:-1], parts[-1])
            existing = {p.uuid for p in album.photos()}
            todo = [i for i in ids if i not in existing]
            for start in range(0, len(todo), BATCH):
                chunk = list(self.lib.photos(uuid=todo[start : start + BATCH]))
                album.add(chunk)
                added += len(chunk)
        return {"placed": added, "removed": 0}

    def _ensure_album(self, folders: list[str], name: str):
        parent = None
        for fname in folders:
            found = None
            subfolders = parent.subfolders if parent else self.lib.folders(top_level=True)
            for f in subfolders:
                if f.name == fname:
                    found = f
                    break
            parent = found or self.lib.create_folder(fname, folder=parent)
        albums = parent.albums if parent else self.lib.albums(top_level=True)
        for a in albums:
            if a.name == name:
                return a
        return self.lib.create_album(name, folder=parent)
