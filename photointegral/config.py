"""读取用户的配置文件（YAML 或 JSON）。"""

from __future__ import annotations

import json
from pathlib import Path

from .strategies import PRESETS, Strategy, build


def load_config(path) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    if str(path).endswith((".yaml", ".yml")):
        try:
            import yaml
        except ImportError as e:
            raise SystemExit("读取 YAML 配置需要 PyYAML：pip install pyyaml（或者改用 JSON）") from e
        return yaml.safe_load(text) or {}
    return json.loads(text)


def strategies_from_config(cfg: dict) -> list[Strategy]:
    """配置格式：

    preset: basic            # 可选，先加载一个预设
    strategies:              # 可选，追加方案
      - date                 # 只写名字 = 默认选项
      - {name: location, level: country, prefix: 足迹}
    rules: [...]             # 可选，自定义规则（见 rules.py）
    """
    specs: list = []
    if cfg.get("preset"):
        if cfg["preset"] not in PRESETS:
            raise ValueError(f"未知预设: {cfg['preset']}（可选: {', '.join(PRESETS)}）")
        specs.extend(PRESETS[cfg["preset"]]["strategies"])
    specs.extend(cfg.get("strategies") or [])
    if cfg.get("rules"):
        specs.append({"name": "rules", "rules": cfg["rules"], "prefix": cfg.get("rules_prefix", "")})
    return [build(s) for s in specs]


def parse_strategy_arg(arg: str) -> dict:
    """命令行写法：date:granularity=year,nested=false"""
    name, _, rest = arg.partition(":")
    spec: dict = {"name": name.strip()}
    for pair in filter(None, rest.split(",")):
        k, _, v = pair.partition("=")
        spec[k.strip()] = _coerce(v.strip())
    return spec


def _coerce(v: str):
    low = v.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if "|" in v:
        return [_coerce(x) for x in v.split("|")]
    for t in (int, float):
        try:
            return t(v)
        except ValueError:
            pass
    return v
