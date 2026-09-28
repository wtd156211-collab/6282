import tempfile
import unittest
from pathlib import Path

from undostack.cli import run_history, run_replay
from undostack.page import render_history
from undostack.parser import parse_script
from undostack.trace import replay


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "samples" / "scripts"
EXPECTED = ROOT / "samples" / "expected"


class SampleTraceTest(unittest.TestCase):
    def test_all_sample_traces_match_byte_for_byte(self):
        for script_path in sorted(SCRIPTS.glob("*.txt")):
            with self.subTest(script_path.stem):
                records = parse_script(script_path.read_text(encoding="utf-8"))
                actual = "".join(f"{line}\n" for line in replay(records))
                expected_path = EXPECTED / script_path.name
                self.assertEqual(actual, expected_path.read_text(encoding="utf-8"))


class PageAndCliTest(unittest.TestCase):
    def test_page_is_deterministic_and_contains_engine_metadata(self):
        scripts = [
            (path.stem, path.read_text(encoding="utf-8"))
            for path in sorted(SCRIPTS.glob("*.txt"))
        ]
        first = render_history(scripts)
        second = render_history(scripts)

        self.assertEqual(first, second)
        self.assertIn('<section data-script="01-typing-20">', first)
        self.assertIn('data-stack="4/8"', first)
        self.assertIn('data-entry="4" data-ops="19-20" data-count="2"', first)
        self.assertIn('class="op color-3" data-op="20"', first)
        self.assertNotIn("fetch(", first)
        self.assertNotIn("https://", first)

    def test_cli_replay_and_history_write_requested_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            trace = temp / "trace.txt"
            page = temp / "history.html"

            self.assertEqual(run_replay(SCRIPTS / "04-branch.txt", trace), 0)
            self.assertEqual(run_history(page), 0)
            self.assertTrue(trace.read_bytes())
            self.assertTrue(page.read_bytes())

    def test_replay_returns_one_for_unavailable_input(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_replay(
                Path(directory) / "missing.txt",
                Path(directory) / "trace.txt",
            )
            self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
