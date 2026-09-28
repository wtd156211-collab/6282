import re

from .model import Record

_CONTENT = re.compile(r"[a-z0-9]+")


def _non_negative_int(value: str, field: str) -> int:
    if not value.isdigit():
        raise ValueError(f"{field} must be a non-negative integer")
    return int(value)


def parse_script(source: str) -> list[Record]:
    records: list[Record] = []
    previous_t = 0

    for line_number, raw_line in enumerate(source.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split(" ")
        kind = parts[0]
        values: dict[str, str] = {}
        for part in parts[1:]:
            if "=" not in part:
                raise ValueError(f"line {line_number}: invalid field {part!r}")
            key, value = part.split("=", 1)
            if key in values:
                raise ValueError(f"line {line_number}: duplicate field {key!r}")
            values[key] = value

        if kind in {"input", "paste"}:
            if set(values) != {"pos", "text", "t"}:
                raise ValueError(f"line {line_number}: invalid {kind} record")
            pos = _non_negative_int(values["pos"], "pos")
            t = _non_negative_int(values["t"], "t")
            text = values["text"]
            if kind == "input" and len(text) != 1:
                raise ValueError(
                    f"line {line_number}: input text must contain one character"
                )
            if kind == "paste" and not 2 <= len(text) <= 8:
                raise ValueError(f"line {line_number}: invalid {kind} text length")
            if _CONTENT.fullmatch(text) is None:
                raise ValueError(f"line {line_number}: text must contain only lowercase letters and digits")
            record = Record(kind=kind, raw=line, t=t, pos=pos, text=text)
        elif kind == "caret":
            if set(values) != {"pos", "t"}:
                raise ValueError(f"line {line_number}: invalid caret record")
            pos = _non_negative_int(values["pos"], "pos")
            t = _non_negative_int(values["t"], "t")
            record = Record(kind=kind, raw=line, t=t, pos=pos)
        elif kind in {"undo", "redo"}:
            if set(values) != {"t"}:
                raise ValueError(f"line {line_number}: invalid {kind} record")
            t = _non_negative_int(values["t"], "t")
            record = Record(kind=kind, raw=line, t=t)
        else:
            raise ValueError(f"line {line_number}: unknown record type {kind!r}")

        if t < previous_t:
            raise ValueError(f"line {line_number}: timestamps must be non-decreasing")
        previous_t = t
        records.append(record)

    return records
