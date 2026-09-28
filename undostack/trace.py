from collections.abc import Iterable, Iterator

from .engine import UndoEngine
from .model import Entry, Record


def format_op_ranges(ops: list[int]) -> str:
    if not ops:
        return "-"

    ranges: list[str] = []
    start = previous = ops[0]
    for op in ops[1:]:
        if op == previous + 1:
            previous = op
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = op
    ranges.append(str(start) if start == previous else f"{start}-{previous}")
    return "+".join(ranges)


def format_entry(entry: Entry) -> str:
    return (
        f"#{entry.id} {entry.kind} n={entry.count} "
        f"ops={format_op_ranges(entry.ops)}"
    )


def format_redo_groups(groups: Iterable[list[Entry]]) -> str:
    rendered = [",".join(f"#{entry.id}" for entry in group) for group in groups]
    rendered = [group for group in rendered if group]
    return "+".join(rendered) if rendered else "-"


def replay(records: Iterable[Record]) -> Iterator[str]:
    engine = UndoEngine()
    for step_number, record in enumerate(records, start=1):
        engine.apply(record)
        entries = ";".join(format_entry(entry) for entry in engine.stack) or "-"
        yield (
            f"{step_number}|{record.raw}|S={len(engine.stack)}/8|"
            f"T={engine.text or '-'}|C={engine.cursor}|"
            f"R={format_redo_groups(engine.redo_groups)}|{entries}"
        )
