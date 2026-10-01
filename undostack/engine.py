"""核心引擎：操作序列解析、连续操作合并、撤销与重做。

口径全部写死在 README.md 第 2 节，不读系统时钟、不取随机数，
同一条脚本跑任意遍结果相同。
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 合并：相邻同类操作的最大毫秒间隔
MERGE_GAP_MS = 500
# 单个栈条目最多覆盖的操作条数
ENTRY_MAX_OPS = 6
# 栈长上界（条目数）
STACK_MAX_ENTRIES = 8
# 单次撤销至少回退的操作条数（栈内不足时弹空）
UNDO_MIN_OPS = 3


class ScriptError(ValueError):
    """操作序列非法或不可用。"""


@dataclass(frozen=True)
class Record:
    """脚本里的一行记录。"""

    kind: str
    raw: str
    t: int
    pos: int | None = None
    text: str | None = None


@dataclass
class Entry:
    """栈条目：同一组连续编辑操作的合并结果。"""

    ident: int
    kind: str
    ops: list[int]
    t_first: int
    t_last: int
    before: tuple[str, int]
    after: tuple[str, int]


@dataclass(frozen=True)
class EntryView:
    """某一步之后栈条目的只读快照。"""

    ident: int
    kind: str
    ops: tuple[int, ...]


@dataclass(frozen=True)
class Step:
    """处理完一条记录之后的完整状态。"""

    record: Record
    op_index: int | None
    text: str
    caret: int
    stack: list[EntryView]
    redo_groups: list[tuple[int, ...]]


_KIND_FIELDS: dict[str, tuple[str, ...]] = {
    "input": ("pos", "text", "t"),
    "paste": ("pos", "text", "t"),
    "caret": ("pos", "t"),
    "undo": ("t",),
    "redo": ("t",),
}


def _parse_int(value: str, what: str, lineno: int) -> int:
    if not value or not all("0" <= ch <= "9" for ch in value):
        raise ScriptError(f"第 {lineno} 行：{what} 必须是非负整数，得到 {value!r}")
    return int(value)


def _parse_record(line: str, lineno: int) -> Record:
    parts = line.split(" ")
    kind = parts[0]
    fields = _KIND_FIELDS.get(kind)
    if fields is None:
        raise ScriptError(f"第 {lineno} 行：未知记录类型 {kind!r}")
    if len(parts) != 1 + len(fields):
        raise ScriptError(f"第 {lineno} 行：字段数不对：{line!r}")
    values: dict[str, str] = {}
    for token in parts[1:]:
        key, sep, value = token.partition("=")
        if not sep or key in values:
            raise ScriptError(f"第 {lineno} 行：字段非法 {token!r}")
        values[key] = value
    if tuple(values.keys()) != fields:
        raise ScriptError(f"第 {lineno} 行：字段顺序/名称不对：{line!r}")

    t = _parse_int(values["t"], "t", lineno)
    if kind in ("undo", "redo"):
        return Record(kind=kind, raw=line, t=t)
    pos = _parse_int(values["pos"], "pos", lineno)
    if kind == "caret":
        return Record(kind=kind, raw=line, t=t, pos=pos)
    text = values["text"]
    if kind == "input" and len(text) != 1:
        raise ScriptError(f"第 {lineno} 行：input 必须插入 1 个字符")
    if kind == "paste" and not 2 <= len(text) <= 8:
        raise ScriptError(f"第 {lineno} 行：paste 必须插入 2..8 个字符")
    if not all(("a" <= ch <= "z") or ("0" <= ch <= "9") for ch in text):
        raise ScriptError(f"第 {lineno} 行：内容只能含小写字母与数字")
    return Record(kind=kind, raw=line, t=t, pos=pos, text=text)


def parse_script(source: str) -> list[Record]:
    """解析脚本文本，空行与 `#` 注释行忽略，t 必须非降序。"""
    if source.startswith("\ufeff"):
        raise ScriptError("文件不允许带 BOM")
    records: list[Record] = []
    last_t = 0
    for lineno, raw in enumerate(source.split("\n"), 1):
        if raw.endswith("\r"):
            raise ScriptError(f"第 {lineno} 行：必须使用 LF 行尾")
        if not raw or raw.startswith("#"):
            continue
        record = _parse_record(raw, lineno)
        if record.t < last_t:
            raise ScriptError(f"第 {lineno} 行：t 必须非降序")
        last_t = record.t
        records.append(record)
    return records


class Engine:
    """状态机：(文本, 光标) + 撤销栈 + 重做分组。"""

    def __init__(self) -> None:
        self.text = ""
        self.caret = 0
        self.stack: list[Entry] = []
        # 重做组按“先撤销在前”排列，redo 取最后一组
        self.redo_groups: list[list[Entry]] = []
        self.op_count = 0
        self._next_entry_id = 1
        self._merge_broken = True

    def iter_steps(self, records: list[Record]):
        for record in records:
            yield self.apply(record)

    def apply(self, record: Record) -> Step:
        if record.kind in ("input", "paste"):
            self._edit(record)
        elif record.kind == "caret":
            self._caret(record)
        elif record.kind == "undo":
            self._undo()
        else:
            self._redo()
        return self._snapshot(record)

    def _edit(self, record: Record) -> None:
        pos = record.pos
        text = record.text
        if pos != self.caret or pos < 0 or pos > len(self.text):
            raise ScriptError(
                f"{record.kind} t={record.t}：pos={pos} 不是当前光标 {self.caret}"
            )
        # 新编辑一律截断重做分支（caret 不截断）
        self.redo_groups.clear()

        self.op_count += 1
        op_index = self.op_count
        before = (self.text, self.caret)
        self.text = self.text[:pos] + text + self.text[pos:]
        self.caret = pos + len(text)

        top = self.stack[-1] if self.stack else None
        can_merge = (
            not self._merge_broken
            and top is not None
            and top.kind == record.kind
            and record.t - top.t_last <= MERGE_GAP_MS
            and pos == top.after[1]
            and len(top.ops) < ENTRY_MAX_OPS
        )
        if can_merge:
            top.ops.append(op_index)
            top.t_last = record.t
            top.after = (self.text, self.caret)
        else:
            entry = Entry(
                ident=self._next_entry_id,
                kind=record.kind,
                ops=[op_index],
                t_first=record.t,
                t_last=record.t,
                before=before,
                after=(self.text, self.caret),
            )
            self._next_entry_id += 1
            self.stack.append(entry)
            if len(self.stack) > STACK_MAX_ENTRIES:
                self.stack.pop(0)
        self._merge_broken = False

    def _caret(self, record: Record) -> None:
        pos = record.pos
        if not 0 <= pos <= len(self.text):
            raise ScriptError(f"caret t={record.t}：pos={pos} 越界")
        # 只有光标真的挪了才打断合并；挪到原位不打断
        if pos != self.caret:
            self._merge_broken = True
            self.caret = pos

    def _undo(self) -> None:
        # 含 noop 在内，undo 之后一定另起条目
        self._merge_broken = True
        if not self.stack:
            return
        popped: list[Entry] = []
        covered = 0
        while self.stack and covered < UNDO_MIN_OPS:
            entry = self.stack.pop()
            popped.append(entry)
            covered += len(entry.ops)
        group = list(reversed(popped))
        self.redo_groups.append(group)
        self.text, self.caret = group[0].before

    def _redo(self) -> None:
        # 含 noop 在内，redo 之后一定另起条目
        self._merge_broken = True
        if not self.redo_groups:
            return
        group = self.redo_groups.pop()
        self.stack.extend(group)
        self.text, self.caret = group[-1].after

    def _snapshot(self, record: Record) -> Step:
        op_index = self.op_count if record.kind in ("input", "paste") else None
        return Step(
            record=record,
            op_index=op_index,
            text=self.text,
            caret=self.caret,
            stack=[EntryView(e.ident, e.kind, tuple(e.ops)) for e in self.stack],
            redo_groups=[tuple(e.ident for e in group) for group in self.redo_groups],
        )


def format_ops(ops: tuple[int, ...] | list[int]) -> str:
    """1-6 区间化、多段用 + 连、单条写单个序号。"""
    parts: list[str] = []
    start = prev = ops[0]
    for value in ops[1:]:
        if value == prev + 1:
            prev = value
            continue
        parts.append(f"{start}" if start == prev else f"{start}-{prev}")
        start = prev = value
    parts.append(f"{start}" if start == prev else f"{start}-{prev}")
    return "+".join(parts)


def format_step(step_no: int, step: Step) -> str:
    """轨迹文件的一行（不含行尾换行）。"""
    entries = ";".join(
        f"#{view.ident} {view.kind} n={len(view.ops)} ops={format_ops(view.ops)}"
        for view in step.stack
    ) or "-"
    redo = "+".join(",".join(f"#{ident}" for ident in group) for group in step.redo_groups) or "-"
    text = step.text if step.text else "-"
    return (
        f"{step_no}|{step.record.raw}|S={len(step.stack)}/{STACK_MAX_ENTRIES}"
        f"|T={text}|C={step.caret}|R={redo}|{entries}"
    )
