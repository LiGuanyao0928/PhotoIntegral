"""照片来源：Mac 照片图库，或从 iPhone 导出/拷贝出来的文件夹。"""

from .folder import FolderSource

__all__ = ["FolderSource", "get_source"]


def get_source(kind: str, **kwargs):
    if kind == "folder":
        return FolderSource(kwargs["path"], hash_files=kwargs.get("hash_files", True))
    if kind == "macos":
        from .macos_photos import MacPhotosSource

        return MacPhotosSource(library=kwargs.get("library"))
    raise ValueError(f"未知来源: {kind}")
