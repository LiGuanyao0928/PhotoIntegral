"""命令行入口。

    photointegral list                         查看所有整理方案和预设
    photointegral wizard                       交互式选择方案（推荐新手）
    photointegral plan  ... -o plan.json       生成整理计划，只预览不改动
    photointegral apply plan.json ...          执行计划
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import load_config, parse_strategy_arg, strategies_from_config
from .plan import Plan
from .sinks import get_sink
from .sources import get_source
from .strategies import PRESETS, STRATEGIES, build


def cmd_list(_args) -> int:
    print("预设（--preset）：")
    for key, p in PRESETS.items():
        print(f"  {key:<10} {p['title']}")
    print("\n整理方案（--strategy 名字:选项=值,...）：")
    for name, cls in STRATEGIES.items():
        print(f"  {name:<11} {cls.description}")
        for opt, (default, desc) in cls.options.items():
            print(f"      {opt}={default!r:<12} {desc}")
    print("  rules       自定义规则，写在配置文件里（见 examples/custom.yaml）")
    return 0


def _source_info(args) -> dict:
    if args.source == "folder":
        if not args.path:
            raise SystemExit("--source folder 需要 --path")
        return {"kind": "folder", "path": args.path}
    return {"kind": "macos", "library": args.library}


def _load_photos(info: dict, hash_files: bool = True):
    kwargs = {k: v for k, v in info.items() if k != "kind"}
    src = get_source(info["kind"], hash_files=hash_files, **kwargs)
    print("正在读取照片……", file=sys.stderr)
    photos = src.photos()
    print(f"读到 {len(photos)} 个文件。", file=sys.stderr)
    return photos


def _collect_strategies(args):
    cfg: dict = {}
    if args.config:
        cfg = load_config(args.config)
    if args.preset:
        cfg["preset"] = args.preset
    strategies = strategies_from_config(cfg)
    strategies += [build(parse_strategy_arg(s)) for s in args.strategy or []]
    if not strategies:
        raise SystemExit("请用 --preset、--strategy 或 --config 选择至少一种整理方案（photointegral list 查看）")
    return strategies


def cmd_plan(args) -> int:
    info = _source_info(args)
    strategies = _collect_strategies(args)
    photos = _load_photos(info)
    plan = Plan.build(photos, strategies, info)
    print(plan.summary())
    if args.output:
        plan.save(args.output)
        print(f"\n计划已保存到 {args.output}，确认无误后运行：photointegral apply {args.output} ...")
    return 0


def _apply(plan: Plan, sink_kind: str, args) -> int:
    kwargs = {}
    if sink_kind == "folder":
        if not args.dest:
            raise SystemExit("--sink folder 需要 --dest")
        kwargs = {"dest": args.dest, "mode": args.mode}
    else:
        kwargs = {"root_folder": args.root_folder or None}
    sink = get_sink(sink_kind, **kwargs)
    if not args.dry_run and not args.yes:
        print(plan.summary(max_albums=30))
        if input("\n确认执行？[y/N] ").strip().lower() not in ("y", "yes"):
            print("已取消。")
            return 1
    result = sink.apply(plan, dry_run=args.dry_run)
    if args.dry_run:
        print("（预演模式，没有做任何改动）")
    else:
        msg = f"完成：放入 {result['placed']} 个文件"
        if result["removed"]:
            msg += f"，移走原文件 {result['removed']} 个"
        print(msg + "。")
    return 0


def _default_sink(plan: Plan) -> str:
    return "macos" if plan.source.get("kind") == "macos" else "folder"


def cmd_apply(args) -> int:
    plan = Plan.load(args.plan)
    return _apply(plan, args.sink or _default_sink(plan), args)


def cmd_run(args) -> int:
    info = _source_info(args)
    plan = Plan.build(_load_photos(info), _collect_strategies(args), info)
    return _apply(plan, args.sink or _default_sink(plan), args)


def _ask(prompt: str, choices: list[str] | None = None, default: str = "") -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        ans = input(f"{prompt}{suffix}: ").strip() or default
        if not choices or ans in choices:
            return ans
        print(f"  请输入: {' / '.join(choices)}")


def cmd_wizard(_args) -> int:
    print("PhotoIntegral 相册整理向导\n")
    print("照片从哪里来？")
    print("  1) Mac 照片 App 图库（开了 iCloud 照片，结果会同步回 iPhone，推荐）")
    print("  2) 电脑上的文件夹（用数据线从 iPhone 导出的照片，Windows / Linux 也能用）")
    src = _ask("选择", ["1", "2"], "1")
    if src == "1":
        info = {"kind": "macos", "library": None}
    else:
        info = {"kind": "folder", "path": _ask("照片文件夹路径")}

    print("\n可以选预设，也可以自己挑方案（多个用逗号或空格分开）：")
    keys = list(PRESETS) + list(STRATEGIES)
    for i, key in enumerate(keys, 1):
        desc = PRESETS[key]["title"] if key in PRESETS else STRATEGIES[key].description
        tag = "预设" if key in PRESETS else "方案"
        print(f"  {i:>2}) [{tag}] {key:<11} {desc}")
    picked = _ask("选择编号", default="1").replace(",", " ").split()
    specs: list = []
    for token in picked:
        if not token.isdigit() or not 1 <= int(token) <= len(keys):
            print(f"  忽略无效编号: {token}")
            continue
        key = keys[int(token) - 1]
        specs.extend(PRESETS[key]["strategies"] if key in PRESETS else [{"name": key}])
    cfg_path = _ask("\n还有自定义规则配置文件吗？（没有就直接回车）")
    strategies = [build(s) for s in specs]
    if cfg_path:
        strategies += strategies_from_config(load_config(cfg_path))
    if not strategies:
        print("没有选择任何方案。")
        return 1

    plan = Plan.build(_load_photos(info), strategies, info)
    print("\n" + plan.summary())
    plan.save("photointegral-plan.json")
    print("\n计划已保存到 photointegral-plan.json")

    ns = argparse.Namespace(dry_run=False, yes=False, dest=None, mode="copy", root_folder="PhotoIntegral")
    if info["kind"] == "folder":
        ns.dest = _ask("归档到哪个文件夹", default="整理后的照片")
        ns.mode = _ask("复制还是移动？copy / link / symlink / move", ["copy", "link", "symlink", "move"], "copy")
    return _apply(plan, _default_sink(plan), ns)


def _add_source_args(p):
    p.add_argument("--source", choices=["macos", "folder"], default="macos", help="照片来源（默认 Mac 照片图库）")
    p.add_argument("--path", help="文件夹来源的路径")
    p.add_argument("--library", help="指定 .photoslibrary 路径（默认系统图库）")
    p.add_argument("--preset", choices=list(PRESETS), help="使用预设方案")
    p.add_argument("--strategy", "-s", action="append", help="添加方案，如 date:granularity=year，可重复")
    p.add_argument("--config", "-c", help="YAML/JSON 配置文件（可含自定义规则）")


def _add_sink_args(p):
    p.add_argument("--sink", choices=["macos", "folder"], help="输出方式（默认与来源一致）")
    p.add_argument("--dest", help="文件夹输出的目标目录")
    p.add_argument("--mode", choices=["copy", "link", "symlink", "move"], default="copy", help="文件夹输出方式")
    p.add_argument("--root-folder", default="PhotoIntegral", help="照片 App 里放相簿的顶层文件夹，传空字符串则不建")
    p.add_argument("--dry-run", action="store_true", help="只显示会做什么，不做改动")
    p.add_argument("--yes", "-y", action="store_true", help="不询问直接执行")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="photointegral", description="整理 iPhone 相册")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="列出所有方案和预设").set_defaults(func=cmd_list)
    sub.add_parser("wizard", help="交互式向导").set_defaults(func=cmd_wizard)

    p = sub.add_parser("plan", help="生成整理计划（只预览）")
    _add_source_args(p)
    p.add_argument("--output", "-o", help="保存计划到 JSON 文件")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("apply", help="执行保存好的计划")
    p.add_argument("plan")
    _add_sink_args(p)
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("run", help="生成计划并立即执行")
    _add_source_args(p)
    _add_sink_args(p)
    p.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, KeyError, FileNotFoundError) as e:
        print(f"错误: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
