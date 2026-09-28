import argparse
import sys
from pathlib import Path

from .page import render_history
from .parser import parse_script
from .trace import replay


def _write_text(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as output:
        output.write(content)


def run_replay(script_path: Path, trace_path: Path) -> int:
    try:
        source = script_path.read_text(encoding="utf-8")
        records = parse_script(source)
        with trace_path.open("w", encoding="utf-8", newline="\n") as output:
            for line in replay(records):
                output.write(line)
                output.write("\n")
    except (OSError, ValueError) as error:
        print(f"replay failed: {error}", file=sys.stderr)
        return 1
    return 0


def run_history(output_path: Path) -> int:
    scripts_directory = Path("samples/scripts")
    try:
        scripts: list[tuple[str, str]] = []
        for script_path in sorted(scripts_directory.glob("*.txt"), key=lambda path: path.name):
            scripts.append((script_path.stem, script_path.read_text(encoding="utf-8")))
        _write_text(output_path, render_history(scripts))
    except (OSError, ValueError) as error:
        print(f"history failed: {error}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m undostack")
    subparsers = parser.add_subparsers(dest="command", required=True)

    replay_parser = subparsers.add_parser("replay")
    replay_parser.add_argument("script")
    replay_parser.add_argument("trace")

    history_parser = subparsers.add_parser("history")
    history_parser.add_argument("page")

    args = parser.parse_args(argv)
    if args.command == "replay":
        return run_replay(Path(args.script), Path(args.trace))
    return run_history(Path(args.page))
