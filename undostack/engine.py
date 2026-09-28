from .model import Entry, Record, State

MAX_ENTRIES = 8
MAX_MERGED_OPS = 6
MERGE_WINDOW_MS = 500
MIN_UNDO_OPS = 3


class UndoEngine:
    def __init__(self) -> None:
        self.text = ""
        self.cursor = 0
        self.stack: list[Entry] = []
        self.redo_groups: list[list[Entry]] = []
        self.next_entry_id = 1
        self.operation_count = 0
        self.record_count = 0
        self.undo_count = 0
        self.redo_count = 0
        self._merge_blocked = False

    def apply(self, record: Record) -> None:
        self.record_count += 1
        if record.kind == "input":
            self._edit(record)
        elif record.kind == "paste":
            self._edit(record)
        elif record.kind == "caret":
            self._caret(record)
        elif record.kind == "undo":
            self.undo()
        elif record.kind == "redo":
            self.redo()
        else:
            raise ValueError(f"unknown record type {record.kind!r}")

    def _edit(self, record: Record) -> None:
        if record.pos != self.cursor:
            raise ValueError(
                f"edit position {record.pos} does not match cursor {self.cursor}"
            )
        if record.text is None:
            raise ValueError("edit record is missing text")

        self.redo_groups.clear()
        before = State(self.text, self.cursor)
        self.text = self.text[: record.pos] + record.text + self.text[record.pos :]
        self.cursor = record.pos + len(record.text)
        after = State(self.text, self.cursor)

        self.operation_count += 1
        top = self.stack[-1] if self.stack else None
        if (
            not self._merge_blocked
            and top is not None
            and top.mergeable
            and top.kind == record.kind
            and record.t - top.end_t <= MERGE_WINDOW_MS
            and record.pos == top.after.cursor
            and top.count < MAX_MERGED_OPS
        ):
            top.ops.append(self.operation_count)
            top.end_t = record.t
            top.after = after
        else:
            entry = Entry(
                id=self.next_entry_id,
                kind=record.kind,
                ops=[self.operation_count],
                start_t=record.t,
                end_t=record.t,
                before=before,
                after=after,
            )
            self.next_entry_id += 1
            self.stack.append(entry)
            if len(self.stack) > MAX_ENTRIES:
                self.stack.pop(0)

        self._merge_blocked = False

    def _caret(self, record: Record) -> None:
        if record.pos is None or not 0 <= record.pos <= len(self.text):
            raise ValueError("caret position is outside the text")
        if record.pos != self.cursor:
            self._merge_blocked = True
        self.cursor = record.pos

    def undo(self) -> None:
        self._merge_blocked = True
        self.undo_count += 1
        if not self.stack:
            return

        popped: list[Entry] = []
        operation_total = 0
        while self.stack and operation_total < MIN_UNDO_OPS:
            entry = self.stack.pop()
            popped.append(entry)
            operation_total += entry.count

        popped.reverse()
        self.text = popped[0].before.text
        self.cursor = popped[0].before.cursor
        self.redo_groups.append(popped)

    def redo(self) -> None:
        self._merge_blocked = True
        self.redo_count += 1
        if not self.redo_groups:
            return

        group = self.redo_groups.pop()
        self.stack.extend(group)
        last = group[-1]
        self.text = last.after.text
        self.cursor = last.after.cursor
