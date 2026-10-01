"""命令行：python -m undostack replay|history。

退出码：0 跑完；1 输入不可用且不写输出；2 用法错误。日志走 stderr。
"""
from __future__ import annotations

import sys
from pathlib import Path

from .engine import Engine, ScriptError, format_step, parse_script
from .page import build_history_html

USAGE = (
    "用法：\n"
    "  python -m undostack replay  <操作序列> <轨迹文件>\n"
    "  python -m undostack history <页面文件>"
)


def _load_script(path: str) -> list:
    script_path = Path(path)
    try:
        source = script_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ScriptError(f"读不了操作序列 {path}：{exc}") from exc
    try:
        return parse_script(source)
    except ScriptError as exc:
        raise ScriptError(f"{path}: {exc}") from exc


def _cmd_replay(script: str, trace: str) -> int:
    try:
        records = _load_script(script)
        # 先完整跑一遍校验，任何一步非法都不写输出文件
        for _ in Engine().iter_steps(records):
            pass
    except ScriptError as exc:
        print(f"replay: {exc}", file=sys.stderr)
        return 1
    engine = Engine()
    try:
        with open(trace, "w", encoding="utf-8", newline="") as out:
            for step_no, step in enumerate(engine.iter_steps(records), 1):
                out.write(format_step(step_no, step))
                out.write("\n")
    except OSError as exc:
        print(f"replay: 写不了轨迹文件 {trace}：{exc}", file=sys.stderr)
        return 1
    print(f"replay: {len(records)} 条记录 -> {trace}", file=sys.stderr)
    return 0


def _cmd_history(page: str) -> int:
    scripts_dir = Path("samples") / "scripts"
    try:
        html_text = build_history_html(scripts_dir)
    except (OSError, ScriptError) as exc:
        print(f"history: {exc}", file=sys.stderr)
        return 1
    try:
        with open(page, "w", encoding="utf-8", newline="") as out:
            out.write(html_text)
    except OSError as exc:
        print(f"history: 写不了页面 {page}：{exc}", file=sys.stderr)
        return 1
    print(f"history: {page}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 3 and args[0] == "replay":
        return _cmd_replay(args[1], args[2])
    if len(args) == 2 and args[0] == "history":
        return _cmd_history(args[1])
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
