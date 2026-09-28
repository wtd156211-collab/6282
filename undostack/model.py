from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Record:
    kind: str
    raw: str
    t: int
    pos: int | None = None
    text: str | None = None


@dataclass(frozen=True, slots=True)
class State:
    text: str
    cursor: int


@dataclass(slots=True)
class Entry:
    id: int
    kind: str
    ops: list[int]
    start_t: int
    end_t: int
    before: State
    after: State
    mergeable: bool = True

    @property
    def count(self) -> int:
        return len(self.ops)
