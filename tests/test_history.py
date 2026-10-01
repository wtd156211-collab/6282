"""history 页面：4.4 五项齐全、数字与 replay 一致、自包含、确定性。"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "samples" / "scripts"
EXPECTED = ROOT / "samples" / "expected"

sys.path.insert(0, str(ROOT))


def build_page(tmp: str) -> str:
    out = Path(tmp) / "history.html"
    proc = subprocess.run(
        [sys.executable, "-m", "undostack", "history", str(out)],
        cwd=ROOT,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr.decode()
    return out.read_text(encoding="utf-8")


def sections(page: str) -> dict[str, str]:
    parts = re.split(r'(?=<section data-script=")', page)
    result = {}
    for part in parts:
        match = re.match(r'<section data-script="([^"]+)">', part)
        if match:
            result[match.group(1)] = part
    return result


class HistoryPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.page = build_page(cls._tmp.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_every_script_has_a_section(self) -> None:
        names = {p.stem for p in SCRIPTS.glob("*.txt")}
        self.assertEqual(set(sections(self.page)), names)

    def test_self_contained(self) -> None:
        for token in ("http://", "https://", "fetch(", "<script", "src=", "@import"):
            self.assertNotIn(token, self.page)

    def test_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.page, build_page(tmp))

    def test_stack_length_matches_replay(self) -> None:
        for script in sorted(SCRIPTS.glob("*.txt"), key=lambda p: p.name):
            with self.subTest(script=script.name):
                last_line = (EXPECTED / script.name).read_text(
                    encoding="utf-8"
                ).splitlines()[-1]
                final_stack = re.search(r"\|S=(\d+)/8\|", last_line).group(1)
                section = sections(self.page)[script.stem]
                self.assertIn(f'data-stack="{final_stack}/8"', section)

    def test_op_rows_match_records(self) -> None:
        for script in sorted(SCRIPTS.glob("*.txt"), key=lambda p: p.name):
            with self.subTest(script=script.name):
                records = [
                    line
                    for line in script.read_text(encoding="utf-8").splitlines()
                    if line and not line.startswith("#")
                ]
                section = sections(self.page)[script.stem]
                rows = re.findall(r'<div class="op" data-op="([^"]+)"', section)
                self.assertEqual(len(rows), len(records))
                edit_ops = [int(v) for v in rows if v != "-"]
                self.assertEqual(edit_ops, list(range(1, len(edit_ops) + 1)))

    def test_entries_match_replay_final_stack(self) -> None:
        for script in sorted(SCRIPTS.glob("*.txt"), key=lambda p: p.name):
            with self.subTest(script=script.name):
                last_line = (EXPECTED / script.name).read_text(
                    encoding="utf-8"
                ).splitlines()[-1]
                entries_field = last_line.split("|")[-1]
                expected = re.findall(
                    r"#(\d+) \w+ n=(\d+) ops=([0-9+\-]+)", entries_field
                )
                expected = [(ident, ops, count) for ident, count, ops in expected]
                section = sections(self.page)[script.stem]
                actual = re.findall(
                    r'<div class="entry" data-entry="(\d+)" data-ops="([^"]+)" '
                    r'data-count="(\d+)"',
                    section,
                )
                self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
