"""自定义规则：用 YAML / JSON 写「满足什么条件 → 放进哪个相簿」。

示例：

    rules:
      - album: "旅行/{year} 日本"
        when: {field: country, op: eq, value: 日本}
      - album: "家人/{year}"
        when:
          any:
            - {field: persons, op: contains, value: 妈妈}
            - {field: persons, op: contains, value: 爸爸}
      - album: "夜景"
        when: {all: [{field: hour, op: gte, value: 19}, {field: is_video, op: eq, value: false}]}
        stop: true   # 命中后不再匹配后面的规则

相簿名可以用 {year} {month:02d} {day:02d} {country} {city} {camera_model} {media_type} {orientation} 等字段。
"""

from __future__ import annotations

import re
from collections import defaultdict

from .models import Photo
from .strategies import Strategy


def _cmp(a, b, fn):
    if a is None:
        return False
    try:
        return fn(a, b)
    except TypeError:
        return False


def _contains(actual, value):
    if actual is None:
        return False
    if isinstance(actual, (list, tuple, set)):
        return any(str(value).lower() == str(x).lower() for x in actual)
    return str(value).lower() in str(actual).lower()


OPS = {
    "eq": lambda a, b: a == b if not isinstance(a, str) else a.lower() == str(b).lower(),
    "ne": lambda a, b: not OPS["eq"](a, b),
    "gt": lambda a, b: _cmp(a, b, lambda x, y: x > y),
    "gte": lambda a, b: _cmp(a, b, lambda x, y: x >= y),
    "lt": lambda a, b: _cmp(a, b, lambda x, y: x < y),
    "lte": lambda a, b: _cmp(a, b, lambda x, y: x <= y),
    "between": lambda a, b: _cmp(a, b, lambda x, y: y[0] <= x <= y[1]),
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
    "contains": _contains,
    "not_contains": lambda a, b: not _contains(a, b),
    "regex": lambda a, b: a is not None and re.search(b, str(a), re.IGNORECASE) is not None,
    "exists": lambda a, b: (a not in (None, "", [])) == bool(b),
}


def matches(photo: Photo, cond: dict) -> bool:
    if not cond:
        return True
    if "all" in cond:
        return all(matches(photo, c) for c in cond["all"])
    if "any" in cond:
        return any(matches(photo, c) for c in cond["any"])
    if "not" in cond:
        return not matches(photo, cond["not"])
    op = cond.get("op", "eq")
    if op not in OPS:
        raise ValueError(f"未知运算符: {op}（可选: {', '.join(OPS)}）")
    value = cond.get("value", True if op == "exists" else None)
    return OPS[op](photo.get(cond["field"]), value)


class _Fields(dict):
    """album 模板取值：缺失的字段显示为「未知」。"""

    def __init__(self, photo: Photo):
        super().__init__()
        self.photo = photo

    def __missing__(self, key):
        value = self.photo.get(key)
        if value is None or value == []:
            return _Unknown()
        if isinstance(value, list):
            return ", ".join(map(str, value))
        return value


class _Unknown(str):
    def __new__(cls):
        return super().__new__(cls, "未知")

    def __format__(self, spec):
        return str(self)


def render_album(template: str, photo: Photo) -> str:
    return template.format_map(_Fields(photo)).strip("/ ")


class RulesStrategy(Strategy):
    name = "rules"
    title = "自定义"
    description = "按你自己写的规则分相簿（见 examples/custom.yaml）。"

    def __init__(self, rules: list[dict], prefix: str | None = None):
        super().__init__(prefix=prefix if prefix is not None else "")
        for i, r in enumerate(rules):
            if "album" not in r:
                raise ValueError(f"第 {i + 1} 条规则缺少 album")
        self.rules = rules

    def group(self, photos):
        groups = defaultdict(list)
        for p in photos:
            for rule in self.rules:
                if matches(p, rule.get("when", {})):
                    groups[render_album(rule["album"], p)].append(p)
                    if rule.get("stop"):
                        break
        return dict(groups)
