"""整理方案。每个方案把照片分到若干「相簿」里，相簿名用 / 表示层级。

一张照片可以同时出现在多个方案的相簿中（和照片 App 里的相簿一样，不会复制原图）。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Callable

from .models import Photo

Groups = dict[str, list[Photo]]
STRATEGIES: dict[str, type["Strategy"]] = {}


def register(cls):
    STRATEGIES[cls.name] = cls
    return cls


class Strategy:
    name = ""
    title = ""
    description = ""
    # 选项名 -> (默认值, 说明)
    options: dict[str, tuple[object, str]] = {}

    def __init__(self, prefix: str | None = None, **opts):
        unknown = set(opts) - set(self.options)
        if unknown:
            raise ValueError(f"方案 {self.name} 不支持选项: {', '.join(sorted(unknown))}")
        self.opts = {k: opts.get(k, default) for k, (default, _) in self.options.items()}
        self.prefix = self.title if prefix is None else prefix

    def group(self, photos: list[Photo]) -> Groups:
        raise NotImplementedError

    def run(self, photos: list[Photo]) -> Groups:
        groups = self.group(photos)
        result = {}
        for album, items in groups.items():
            if not items:
                continue
            full = f"{self.prefix}/{album}" if self.prefix else album
            result[full] = items
        return result


def _bucket(photos: list[Photo], key: Callable[[Photo], str | None]) -> Groups:
    groups: Groups = defaultdict(list)
    for p in photos:
        k = key(p)
        if k:
            groups[k].append(p)
    return dict(groups)


SEASONS = {12: "冬", 1: "冬", 2: "冬", 3: "春", 4: "春", 5: "春", 6: "夏", 7: "夏", 8: "夏", 9: "秋", 10: "秋", 11: "秋"}


@register
class ByDate(Strategy):
    name = "date"
    title = "按日期"
    description = "按年 / 月 / 日 / 季节建相簿，例如「按日期/2024/2024-05」。"
    options = {
        "granularity": ("month", "year | month | day | season"),
        "nested": (True, "是否按年分层（2024/2024-05），否则平铺（2024-05）"),
    }

    def group(self, photos):
        g = self.opts["granularity"]
        nested = self.opts["nested"]

        def key(p: Photo):
            if not p.date:
                return "未知日期"
            d = p.date
            if g == "year":
                return f"{d.year}"
            if g == "month":
                leaf = f"{d.year}-{d.month:02d}"
            elif g == "day":
                leaf = f"{d.year}-{d.month:02d}-{d.day:02d}"
            elif g == "season":
                # 12 月算入下一年的冬季
                year = d.year + 1 if d.month == 12 else d.year
                leaf = f"{year} {SEASONS[d.month]}"
                return f"{year}/{leaf}" if nested else leaf
            else:
                raise ValueError(f"granularity 不支持: {g}")
            return f"{d.year}/{leaf}" if nested else leaf

        return _bucket(photos, key)


@register
class ByLocation(Strategy):
    name = "location"
    title = "按地点"
    description = "按国家 / 城市建相簿。没有地名时按 GPS 坐标网格分组（Mac 图库自带地名）。"
    options = {
        "level": ("city", "country | city"),
        "grid": (1.0, "没有地名时用的坐标网格大小（度），1 度约 100 公里"),
        "include_unknown": (False, "是否为没有位置的照片建「无位置」相簿"),
    }

    def group(self, photos):
        level, grid = self.opts["level"], float(self.opts["grid"])

        def key(p: Photo):
            if p.country or p.city:
                country = p.country or "未知国家"
                if level == "country" or not p.city:
                    return country
                return f"{country}/{p.city}"
            if p.has_location:
                lat = int(p.latitude // grid) * grid
                lon = int(p.longitude // grid) * grid
                ns = "N" if lat >= 0 else "S"
                ew = "E" if lon >= 0 else "W"
                return f"坐标 {ns}{abs(lat):g} {ew}{abs(lon):g}"
            return "无位置" if self.opts["include_unknown"] else None

        return _bucket(photos, key)


@register
class ByMediaType(Strategy):
    name = "media_type"
    title = "按类型"
    description = "把截图、视频、实况、自拍、连拍、人像、全景分别归类。"
    options = {
        "types": (
            ["screenshot", "video", "live", "selfie", "burst", "portrait", "panorama"],
            "要分出来的类型",
        ),
    }
    LABELS = {
        "screenshot": ("截图", lambda p: p.is_screenshot),
        "video": ("视频", lambda p: p.is_video and not p.is_live),
        "live": ("实况照片", lambda p: p.is_live),
        "selfie": ("自拍", lambda p: p.is_selfie),
        "burst": ("连拍", lambda p: p.is_burst),
        "portrait": ("人像模式", lambda p: p.is_portrait),
        "panorama": ("全景", lambda p: p.is_panorama),
        "favorite": ("个人收藏", lambda p: p.is_favorite),
    }

    def group(self, photos):
        groups: Groups = {}
        for t in self.opts["types"]:
            if t not in self.LABELS:
                raise ValueError(f"未知类型: {t}（可选: {', '.join(self.LABELS)}）")
            label, pred = self.LABELS[t]
            groups[label] = [p for p in photos if pred(p)]
        return groups


@register
class ByCamera(Strategy):
    name = "camera"
    title = "按设备"
    description = "按拍摄设备分组；没有相机信息的通常是保存的图片 / 微信图片 / 截图。"
    options = {"unknown_name": ("保存的图片", "没有相机信息时的相簿名")}

    def group(self, photos):
        def key(p: Photo):
            if p.is_screenshot:
                return None
            if p.camera_model:
                return p.camera_model
            return None if p.is_video else self.opts["unknown_name"]

        return _bucket(photos, key)


@register
class ByPeople(Strategy):
    name = "people"
    title = "按人物"
    description = "每个已命名的人物一个相簿（需要 Mac 照片 App 的人物识别）。"
    options = {"min_count": (3, "照片少于这个数的人物不建相簿")}

    def group(self, photos):
        groups: Groups = defaultdict(list)
        for p in photos:
            for person in p.persons:
                groups[person].append(p)
        return {k: v for k, v in groups.items() if len(v) >= self.opts["min_count"]}


@register
class Events(Strategy):
    name = "events"
    title = "按事件"
    description = "把时间上连续的照片聚成一次「出游 / 活动」，例如「2024-05-01~05-03 京都」。"
    options = {
        "gap_hours": (8.0, "两张照片间隔超过多少小时就算新事件"),
        "min_photos": (15, "少于这么多张的不单独成相簿"),
    }

    def group(self, photos):
        dated = sorted((p for p in photos if p.date), key=lambda p: p.date)
        gap = timedelta(hours=float(self.opts["gap_hours"]))
        clusters: list[list[Photo]] = []
        for p in dated:
            if clusters and p.date - clusters[-1][-1].date <= gap:
                clusters[-1].append(p)
            else:
                clusters.append([p])
        groups: Groups = {}
        for c in clusters:
            if len(c) < self.opts["min_photos"]:
                continue
            start, end = c[0].date, c[-1].date
            name = f"{start:%Y-%m-%d}"
            if end.date() != start.date():
                name += f"~{end:%m-%d}" if end.year == start.year else f"~{end:%Y-%m-%d}"
            place = _most_common([p.city or p.country for p in c])
            if place:
                name += f" {place}"
            groups[name] = groups.get(name, []) + c
        return groups


def _most_common(values):
    counts: dict[str, int] = defaultdict(int)
    for v in values:
        if v:
            counts[v] += 1
    return max(counts, key=counts.get) if counts else None


def _keep_best(group: list[Photo]) -> Photo:
    """一组重复照片里保留哪张：收藏的 > 分辨率高的 > 文件大的 > 最早的。"""
    return max(
        group,
        key=lambda p: (p.is_favorite, p.width * p.height, p.size, -(p.date.timestamp() if p.date else 0)),
    )


@register
class Duplicates(Strategy):
    name = "duplicates"
    title = "待清理"
    description = "找出内容完全相同的重复照片。每组保留最好的一张，其余放进「待清理/重复」，不会直接删除。"
    options = {"include_kept": (False, "是否把保留的那张也放进「重复-保留」相簿方便对照")}

    def group(self, photos):
        by_fp: Groups = defaultdict(list)
        for p in photos:
            if p.fingerprint:
                by_fp[p.fingerprint].append(p)
        dupes, kept = [], []
        for group in by_fp.values():
            if len(group) < 2:
                continue
            best = _keep_best(group)
            kept.append(best)
            dupes.extend(p for p in group if p is not best)
        groups = {"重复": dupes}
        if self.opts["include_kept"]:
            groups["重复-保留"] = kept
        return groups


def dhash(path, size: int = 8) -> int | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as img:
            img = img.convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
            px = img.tobytes()
    except Exception:
        return None
    bits = 0
    for row in range(size):
        for col in range(size):
            left = px[row * (size + 1) + col]
            right = px[row * (size + 1) + col + 1]
            bits = (bits << 1) | (left > right)
    return bits


@register
class Similar(Strategy):
    name = "similar"
    title = "待清理"
    description = "用感知哈希找出连拍、重复拍的相似照片，每组一个相簿，方便挑一张留下（需要原图文件）。"
    options = {
        "threshold": (6, "哈希差异 ≤ 这个值算相似（0~64，越小越严格）"),
        "window_minutes": (10.0, "只比较拍摄时间相差这么多分钟以内的照片"),
    }

    def group(self, photos):
        candidates = [p for p in photos if p.path and not p.is_video]
        candidates.sort(key=lambda p: (p.date is None, p.date))
        hashes = {id(p): dhash(p.path) for p in candidates}
        window = timedelta(minutes=float(self.opts["window_minutes"]))
        threshold = int(self.opts["threshold"])

        parent = {id(p): id(p) for p in candidates}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for i, a in enumerate(candidates):
            ha = hashes[id(a)]
            if ha is None:
                continue
            for b in candidates[i + 1 :]:
                if a.date and b.date and b.date - a.date > window:
                    break
                hb = hashes[id(b)]
                if hb is not None and bin(ha ^ hb).count("1") <= threshold:
                    parent[find(id(b))] = find(id(a))

        clusters: dict[int, list[Photo]] = defaultdict(list)
        for p in candidates:
            clusters[find(id(p))].append(p)
        groups: Groups = {}
        n = 0
        for c in clusters.values():
            if len(c) < 2:
                continue
            n += 1
            label = f"{c[0].date:%Y-%m-%d}" if c[0].date else "未知日期"
            groups[f"相似/{n:03d} {label} ({len(c)}张)"] = c
        return groups


@register
class Large(Strategy):
    name = "large"
    title = "待清理"
    description = "找出占空间的大文件和长视频，方便腾出 iPhone 存储空间。"
    options = {
        "min_mb": (50.0, "超过多少 MB 算大文件"),
        "long_video_seconds": (180.0, "超过多少秒算长视频（0 表示不检查）"),
    }

    def group(self, photos):
        groups = {"大文件": [p for p in photos if p.size_mb >= float(self.opts["min_mb"])]}
        limit = float(self.opts["long_video_seconds"])
        if limit > 0:
            groups["长视频"] = [p for p in photos if p.is_video and p.duration >= limit]
        return groups


@register
class Screenshots(Strategy):
    name = "screenshots"
    title = "待清理"
    description = "把旧截图单独拎出来（截图往往用完就没用了）。"
    options = {"older_than_days": (30, "只挑多少天以前的截图")}

    def group(self, photos):
        from datetime import datetime

        cutoff = datetime.now() - timedelta(days=int(self.opts["older_than_days"]))
        return {"旧截图": [p for p in photos if p.is_screenshot and p.date and p.date < cutoff]}


PRESETS: dict[str, dict] = {
    "basic": {
        "title": "简洁：按月份 + 按类型",
        "strategies": [{"name": "date", "granularity": "month"}, {"name": "media_type"}],
    },
    "timeline": {
        "title": "时间线：按年 / 月 + 事件",
        "strategies": [{"name": "date", "granularity": "month"}, {"name": "events"}],
    },
    "travel": {
        "title": "旅行：按地点 + 事件",
        "strategies": [{"name": "location", "level": "city"}, {"name": "events", "min_photos": 20}],
    },
    "cleanup": {
        "title": "清理空间：重复 + 相似 + 大文件 + 旧截图（只归类，不删除）",
        "strategies": [{"name": "duplicates"}, {"name": "similar"}, {"name": "large"}, {"name": "screenshots"}],
    },
    "full": {
        "title": "全部：日期、地点、类型、人物、设备、事件、清理",
        "strategies": [
            {"name": "date"},
            {"name": "location"},
            {"name": "media_type"},
            {"name": "people"},
            {"name": "camera"},
            {"name": "events"},
            {"name": "duplicates"},
            {"name": "large"},
        ],
    },
}


def build(spec: dict | str) -> Strategy:
    """从配置构造方案：{"name": "date", "prefix": "...", 其他选项...}。"""
    if isinstance(spec, str):
        spec = {"name": spec}
    spec = dict(spec)
    name = spec.pop("name")
    if name == "rules":
        from .rules import RulesStrategy

        return RulesStrategy(spec.pop("rules"), prefix=spec.pop("prefix", None))
    if name not in STRATEGIES:
        raise ValueError(f"未知方案: {name}（可选: {', '.join(STRATEGIES)}, rules）")
    prefix = spec.pop("prefix", None)
    return STRATEGIES[name](prefix=prefix, **spec)
