"""把 samples/scripts/ 全部序列摊成一个自包含、确定性的 HTML 页面。

左列是操作记录、右列是引擎给出的最终栈条目，同一条目的色块同时
涂在右列条目和它覆盖的左列记录上；页面上所有数字、分组只来自引擎。
"""
from __future__ import annotations

import html
from pathlib import Path

from .engine import Engine, format_ops, parse_script

_PAGE_HEAD = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>撤销栈合并对照</title>
<style>
* { box-sizing: border-box; }
body { margin: 0; background: #f4f5f7; color: #1f2430;
  font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; }
header { padding: 20px 28px 8px; }
header h1 { margin: 0 0 4px; font-size: 20px; }
header p { margin: 0; color: #666; font-size: 13px; }
section { background: #fff; margin: 16px 28px; border: 1px solid #dfe3e8;
  border-radius: 8px; padding: 16px 20px; }
section h2 { margin: 0 0 6px; font-size: 16px; }
.meta { margin: 0 0 14px; font-size: 13px; color: #555; }
.meta .stack { display: inline-block; padding: 1px 8px; border-radius: 10px;
  background: #eef1f5; color: #1f2430; }
.cols { display: flex; gap: 20px; align-items: flex-start; }
.colh { font-size: 12px; color: #888; margin: 0 0 6px; }
.ops { flex: 1 1 56%; }
.entries { flex: 1 1 44%; }
.op, .entry { border-radius: 4px; padding: 3px 8px; margin: 2px 0;
  font: 12px/1.5 "SFMono-Regular", Consolas, monospace; }
.op { border-left: 4px solid #d8dce2; background: #fafbfc; }
.op .oid { display: inline-block; min-width: 3.2em; color: #8a909c; }
.entry { border: 1px solid #d8dce2; display: flex; gap: 10px;
  align-items: baseline; }
.entry .chip { display: inline-block; width: 12px; height: 12px; border-radius: 3px;
  border: 1px solid rgba(0,0,0,.15); align-self: center; }
.entry .eid { font-weight: 600; min-width: 2.6em; }
.entry .en { margin-left: auto; color: #555; }
</style>
</head>
<body>
<header>
<h1>撤销栈合并对照</h1>
<p>左列为操作记录，右列为最终栈条目；同色表示条目覆盖的操作。栈长上界 8，单条目最多 6 条，单次撤销至少回退 3 条。</p>
</header>
"""

_PAGE_TAIL = "</body>\n</html>\n"


def _colors(index: int, total: int) -> tuple[str, str]:
    hue = (index * 137) % 360
    return f"hsl({hue}, 72%, 42%)", f"hsl({hue}, 86%, 90%)"


def _left_row(step, color_by_op: dict[int, tuple[str, str]]) -> str:
    record = step.record
    op_index = step.op_index
    if op_index is not None:
        fg, bg = color_by_op.get(op_index, ("#d8dce2", "#fafbfc"))
        detail = (
            f"{record.kind} pos={record.pos} "
            f"text={html.escape(record.text)} t={record.t}"
        )
    else:
        fg, bg = "#d8dce2", "#fafbfc"
        detail = html.escape(record.raw)
    data_op = "-" if op_index is None else str(op_index)
    return (
        f'<div class="op" data-op="{data_op}" '
        f'style="background:{bg};border-left-color:{fg}">'
        f'<span class="oid">{("#" + str(op_index)) if op_index is not None else ""}</span> '
        f"{detail}</div>\n"
    )


def _build_section(path: Path) -> str:
    records = parse_script(path.read_text(encoding="utf-8"))
    engine = Engine()
    steps = list(engine.iter_steps(records))
    final_stack = steps[-1].stack if steps else []

    color_by_op: dict[int, tuple[str, str]] = {}
    entry_rows: list[str] = []
    for index, view in enumerate(final_stack):
        fg, bg = _colors(index, len(final_stack))
        for op_index in view.ops:
            color_by_op[op_index] = (fg, bg)
        entry_rows.append(
            f'<div class="entry" data-entry="{view.ident}" '
            f'data-ops="{format_ops(view.ops)}" data-count="{len(view.ops)}" '
            f'style="background:{bg}">'
            f'<span class="chip" style="background:{fg}"></span>'
            f'<span class="eid">#{view.ident}</span>'
            f'<span class="ekind">{view.kind}</span>'
            f'<span class="en">覆盖 {len(view.ops)} 条 · ops={format_ops(view.ops)}</span>'
            f"</div>\n"
        )

    undo_count = sum(1 for record in records if record.kind == "undo")
    redo_count = sum(1 for record in records if record.kind == "redo")
    stack_label = f"{len(final_stack)}/8"
    left_rows = "".join(_left_row(step, color_by_op) for step in steps)

    return (
        f'<section data-script="{path.stem}">\n'
        f"<h2>{html.escape(path.stem)}</h2>\n"
        f'<p class="meta">记录数 {len(records)} · 操作 {engine.op_count} 条 · '
        f"撤销 {undo_count} 次 · 重做 {redo_count} 次 · "
        f'<span class="stack" data-stack="{stack_label}">栈长 {stack_label}</span></p>\n'
        f'<div class="cols">\n'
        f'<div class="ops"><p class="colh">操作序列</p>\n{left_rows}</div>\n'
        f'<div class="entries"><p class="colh">合并后的栈条目（栈底→栈顶）</p>\n'
        f'{"".join(entry_rows)}</div>\n'
        f"</div>\n"
        f"</section>\n"
    )


def build_history_html(scripts_dir: str | Path) -> str:
    directory = Path(scripts_dir)
    paths = sorted(directory.glob("*.txt"), key=lambda p: p.name)
    if not paths:
        raise FileNotFoundError(f"没有找到操作序列：{directory}")
    sections = "".join(_build_section(path) for path in paths)
    return _PAGE_HEAD + sections + _PAGE_TAIL
