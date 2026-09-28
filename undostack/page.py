from html import escape

from .engine import MAX_ENTRIES, UndoEngine
from .model import Record
from .parser import parse_script
from .trace import format_entry, format_op_ranges


def analyze_script(source: str) -> dict[str, object]:
    records = parse_script(source)
    engine = UndoEngine()
    rows: list[dict[str, object]] = []

    for record in records:
        operation_id = engine.operation_count + 1 if record.kind in {"input", "paste"} else None
        engine.apply(record)
        rows.append({"record": record, "operation_id": operation_id})

    coverage: dict[int, int] = {}
    for position, entry in enumerate(engine.stack):
        for operation_id in entry.ops:
            coverage[operation_id] = position

    return {
        "rows": rows,
        "entries": list(engine.stack),
        "coverage": coverage,
        "record_count": engine.record_count,
        "operation_count": engine.operation_count,
        "undo_count": engine.undo_count,
        "redo_count": engine.redo_count,
        "stack_length": len(engine.stack),
    }


def _record_details(record: Record) -> str:
    if record.kind in {"input", "paste"}:
        return (
            f"{record.kind} · pos={record.pos} · "
            f"text={record.text} · t={record.t}"
        )
    if record.kind == "caret":
        return f"caret · pos={record.pos} · t={record.t}"
    return f"{record.kind} · t={record.t}"


def _render_script(name: str, analysis: dict[str, object]) -> str:
    rows = analysis["rows"]
    entries = analysis["entries"]
    coverage = analysis["coverage"]
    stack_length = analysis["stack_length"]

    operation_rows: list[str] = []
    for row in rows:
        record = row["record"]
        operation_id = row["operation_id"]
        color_class = ""
        if operation_id is not None and operation_id in coverage:
            color_class = f" color-{coverage[operation_id]}"
        operation_label = "-" if operation_id is None else str(operation_id)
        operation_rows.append(
            f'<div class="op{color_class}" data-op="{operation_label}">'
            f'<span class="op-index">{operation_label}</span>'
            f"<span>{escape(_record_details(record))}</span></div>"
        )

    entry_rows: list[str] = []
    for position, entry in enumerate(entries):
        entry_rows.append(
            f'<div class="entry color-{position}" data-entry="{entry.id}" '
            f'data-ops="{format_op_ranges(entry.ops)}" data-count="{entry.count}">'
            f'<span class="swatch"></span><span>{escape(format_entry(entry))}</span>'
            "</div>"
        )

    return f"""<section data-script="{escape(name)}">
  <header>
    <h2>{escape(name)}</h2>
    <div class="metrics">
      <span data-stack="{stack_length}/{MAX_ENTRIES}">栈长 {stack_length}/{MAX_ENTRIES}</span>
      <span>记录 {analysis['record_count']}</span>
      <span>操作 {analysis['operation_count']}</span>
      <span>撤销 {analysis['undo_count']}</span>
      <span>重做 {analysis['redo_count']}</span>
    </div>
  </header>
  <div class="board">
    <div class="pane">
      <h3>操作序列</h3>
      <div class="list">
        {''.join(operation_rows)}
      </div>
    </div>
    <div class="pane">
      <h3>合并后的栈条目</h3>
      <div class="list">
        {''.join(entry_rows) if entry_rows else '<div class="empty">-</div>'}
      </div>
    </div>
  </div>
</section>"""


def render_history(scripts: list[tuple[str, str]]) -> str:
    sections = [
        _render_script(name, analyze_script(source))
        for name, source in sorted(scripts, key=lambda item: item[0])
    ]
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>撤销栈合并视图</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f6f7f9;
      color: #172033;
    }}
    body {{ margin: 0; padding: 24px; }}
    h1 {{ margin: 0 0 20px; font-size: 24px; }}
    section {{
      background: #fff;
      border: 1px solid #d9dee8;
      border-radius: 12px;
      margin: 0 0 24px;
      padding: 18px;
      box-shadow: 0 1px 3px rgb(20 30 50 / 8%);
    }}
    header {{ display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap; }}
    h2 {{ margin: 0; font-size: 19px; }}
    h3 {{ margin: 0 0 10px; font-size: 14px; color: #5b6575; }}
    .metrics {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .metrics span {{
      background: #eef2f7;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 13px;
    }}
    .board {{ display: grid; grid-template-columns: minmax(280px, 1fr) minmax(280px, 1fr); gap: 16px; margin-top: 16px; }}
    .pane {{
      border: 1px solid #e2e6ee;
      border-radius: 10px;
      min-width: 0;
      padding: 12px;
    }}
    .list {{ display: flex; flex-direction: column; gap: 6px; max-height: 520px; overflow: auto; }}
    .op, .entry {{
      align-items: center;
      border-radius: 8px;
      display: flex;
      gap: 8px;
      padding: 6px 8px;
      font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
      font-size: 13px;
    }}
    .op-index {{
      border-radius: 6px;
      color: #657085;
      min-width: 30px;
      text-align: right;
    }}
    .swatch {{ width: 10px; height: 10px; border-radius: 3px; flex: none; }}
    .empty {{ color: #748094; padding: 8px; }}
    .color-0 {{ background: #dbeafe; }}
    .color-0 .swatch {{ background: #2563eb; }}
    .color-1 {{ background: #dcfce7; }}
    .color-1 .swatch {{ background: #16a34a; }}
    .color-2 {{ background: #ffedd5; }}
    .color-2 .swatch {{ background: #ea580c; }}
    .color-3 {{ background: #fce7f3; }}
    .color-3 .swatch {{ background: #db2777; }}
    .color-4 {{ background: #ede9fe; }}
    .color-4 .swatch {{ background: #7c3aed; }}
    .color-5 {{ background: #cffafe; }}
    .color-5 .swatch {{ background: #0891b2; }}
    .color-6 {{ background: #fef9c3; }}
    .color-6 .swatch {{ background: #ca8a04; }}
    .color-7 {{ background: #fee2e2; }}
    .color-7 .swatch {{ background: #dc2626; }}
    @media (max-width: 760px) {{ .board {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <h1>撤销栈合并视图</h1>
  {''.join(sections)}
</body>
</html>
"""
