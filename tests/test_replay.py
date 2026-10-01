"""replay 正确性、两条界、分支截断与确定性（只读 samples/）。"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "samples" / "scripts"
EXPECTED = ROOT / "samples" / "expected"

sys.path.insert(0, str(ROOT))

from undostack.engine import (  # noqa: E402
    STACK_MAX_ENTRIES,
    UNDO_MIN_OPS,
    Engine,
    parse_script,
)


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "undostack", *args],
        cwd=ROOT,
        capture_output=True,
    )


def script_paths() -> list[Path]:
    return sorted(SCRIPTS.glob("*.txt"), key=lambda p: p.name)


class ReplayMatchesExpectedTest(unittest.TestCase):
    def test_all_samples_byte_identical(self) -> None:
        for script in script_paths():
            with self.subTest(script=script.name):
                expected = (EXPECTED / script.name).read_bytes()
                with tempfile.TemporaryDirectory() as tmp:
                    out = Path(tmp) / "trace.txt"
                    proc = run_cli("replay", str(script), str(out))
                    self.assertEqual(proc.returncode, 0, proc.stderr.decode())
                    self.assertEqual(out.read_bytes(), expected)

    def test_replay_is_deterministic(self) -> None:
        for script in script_paths():
            with self.subTest(script=script.name):
                with tempfile.TemporaryDirectory() as tmp:
                    first = Path(tmp) / "a.txt"
                    second = Path(tmp) / "b.txt"
                    self.assertEqual(run_cli("replay", str(script), str(first)).returncode, 0)
                    self.assertEqual(run_cli("replay", str(script), str(second)).returncode, 0)
                    self.assertEqual(first.read_bytes(), second.read_bytes())


class CliExitCodeTest(unittest.TestCase):
    def test_usage_error_is_2(self) -> None:
        self.assertEqual(run_cli().returncode, 2)
        self.assertEqual(run_cli("replay", "only-one-arg").returncode, 2)
        self.assertEqual(run_cli("nope").returncode, 2)

    def test_missing_input_is_1_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "trace.txt"
            proc = run_cli("replay", str(Path(tmp) / "absent.txt"), str(out))
            self.assertEqual(proc.returncode, 1)
            self.assertFalse(out.exists())

    def test_invalid_script_is_1_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.txt"
            bad.write_text("input pos=5 text=a t=0\n", encoding="utf-8")
            out = Path(tmp) / "trace.txt"
            proc = run_cli("replay", str(bad), str(out))
            self.assertEqual(proc.returncode, 1)
            self.assertFalse(out.exists())


class BoundsTest(unittest.TestCase):
    """栈长上界 8、单次撤销回退 3..8 条（不足时弹空）。"""

    def test_stack_never_exceeds_cap(self) -> None:
        for script in script_paths():
            with self.subTest(script=script.name):
                records = parse_script(script.read_text(encoding="utf-8"))
                for step in Engine().iter_steps(records):
                    self.assertLessEqual(len(step.stack), STACK_MAX_ENTRIES)

    def test_undo_reverts_between_min_and_cap(self) -> None:
        for script in script_paths():
            with self.subTest(script=script.name):
                records = parse_script(script.read_text(encoding="utf-8"))
                previous = None
                for step in Engine().iter_steps(records):
                    if step.record.kind == "undo" and previous is not None:
                        remaining = {view.ident for view in step.stack}
                        popped = [v for v in previous.stack if v.ident not in remaining]
                        if popped:
                            covered = sum(len(v.ops) for v in popped)
                            self.assertLessEqual(covered, 8)
                            self.assertTrue(
                                covered >= UNDO_MIN_OPS or not step.stack,
                                f"undo 只退了 {covered} 条且栈未空",
                            )
                        else:
                            self.assertFalse(previous.stack, "非空栈 undo 不该是 noop")
                    previous = step


class BranchTest(unittest.TestCase):
    def test_new_edit_truncates_redo_but_caret_does_not(self) -> None:
        records = parse_script(
            (SCRIPTS / "04-branch.txt").read_text(encoding="utf-8")
        )
        steps = list(Engine().iter_steps(records))
        by_raw = {step.record.raw: step for step in steps}
        # 撤销后 caret 不截断重做组
        self.assertEqual(by_raw["caret pos=7 t=1100"].redo_groups, [(2,)])
        # 新编辑把重做组全部丢弃，之后的 redo 是 noop
        self.assertEqual(by_raw["input pos=2 text=q t=1400"].redo_groups, [])
        self.assertEqual(by_raw["redo t=1500"].redo_groups, [])

    def test_noop_undo_and_redo_keep_state(self) -> None:
        records = parse_script(
            (SCRIPTS / "06-edges.txt").read_text(encoding="utf-8")
        )
        steps = list(Engine().iter_steps(records))
        noop_undo = next(s for s in steps if s.record.raw == "undo t=160")
        self.assertEqual(noop_undo.stack, [])
        self.assertEqual(noop_undo.text, "")
        self.assertEqual(noop_undo.redo_groups, [(2,), (1,)])
        noop_redo = next(s for s in steps if s.record.raw == "redo t=190")
        self.assertEqual(noop_redo.redo_groups, [])
        self.assertEqual(len(noop_redo.stack), 2)


if __name__ == "__main__":
    unittest.main()
