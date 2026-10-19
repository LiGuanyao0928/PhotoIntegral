"""执行计划：在 Mac 照片 App 里建相簿，或者把文件归档到文件夹。"""

from .folder import FolderSink

__all__ = ["FolderSink", "get_sink"]


def get_sink(kind: str, **kwargs):
    if kind == "folder":
        return FolderSink(kwargs["dest"], mode=kwargs.get("mode", "copy"))
    if kind == "macos":
        from .macos_photos import MacPhotosSink

        return MacPhotosSink(root_folder=kwargs.get("root_folder"))
    raise ValueError(f"未知输出: {kind}")
