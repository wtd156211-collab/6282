import unittest

from undostack import UndoEngine, parse_script


def records(text: str):
    return parse_script(text)


def run(text: str) -> UndoEngine:
    engine = UndoEngine()
    for record in records(text):
        engine.apply(record)
    return engine


class MergeRulesTest(unittest.TestCase):
    def test_boundary_time_position_and_capacity(self):
        engine = run(
            "\n".join(
                [
                    "input pos=0 text=a t=0",
                    "input pos=1 text=b t=500",
                    "input pos=2 text=c t=1001",
                    "input pos=3 text=d t=1040",
                ]
            )
        )

        self.assertEqual([entry.count for entry in engine.stack], [2, 2])
        self.assertEqual([entry.ops for entry in engine.stack], [[1, 2], [3, 4]])

    def test_entry_caps_at_six_operations(self):
        lines = [
            f"input pos={index} text=a t={index * 10}" for index in range(7)
        ]
        engine = run("\n".join(lines))

        self.assertEqual(len(engine.stack), 2)
        self.assertEqual(engine.stack[0].count, 6)
        self.assertEqual(engine.stack[1].count, 1)

    def test_different_kind_does_not_merge(self):
        engine = run(
            "paste pos=0 text=ab t=0\n"
            "paste pos=2 text=cd t=10\n"
            "input pos=4 text=e t=20\n"
            "input pos=5 text=f t=30\n"
            "paste pos=6 text=gh t=40\n"
        )

        self.assertEqual([entry.kind for entry in engine.stack], ["paste", "input", "paste"])
        self.assertEqual([entry.count for entry in engine.stack], [2, 2, 1])

    def test_caret_same_position_does_not_break_merge(self):
        engine = run(
            "input pos=0 text=a t=0\n"
            "caret pos=1 t=100\n"
            "input pos=1 text=b t=200\n"
        )

        self.assertEqual(len(engine.stack), 1)
        self.assertEqual(engine.stack[0].ops, [1, 2])

    def test_caret_movement_blocks_once_then_editing_resumes_merge(self):
        engine = run(
            "input pos=0 text=a t=0\n"
            "caret pos=0 t=100\n"
            "input pos=0 text=b t=200\n"
            "input pos=1 text=c t=300\n"
        )

        self.assertEqual([entry.ops for entry in engine.stack], [[1], [2, 3]])


class UndoRedoTest(unittest.TestCase):
    def test_undo_pops_at_least_three_operations(self):
        lines = [
            f"input pos={index} text=a t={index * 10}"
            for index in range(9)
        ]
        lines.append("undo t=1000")
        engine = run("\n".join(lines))

        self.assertEqual(engine.text, "a" * 6)
        self.assertEqual(engine.cursor, 6)
        self.assertEqual(len(engine.stack), 1)
        self.assertEqual([entry.ops for entry in engine.redo_groups[0]], [[7, 8, 9]])

    def test_undo_with_fewer_than_three_operations_clears_stack(self):
        engine = run(
            "input pos=0 text=a t=0\n"
            "input pos=1 text=b t=100\n"
            "undo t=200\n"
        )

        self.assertEqual(engine.stack, [])
        self.assertEqual(engine.text, "")
        self.assertEqual(engine.cursor, 0)

    def test_empty_undo_and_redo_are_noops_but_break_merge(self):
        engine = run(
            "input pos=0 text=a t=0\n"
            "undo t=100\n"
            "redo t=200\n"
            "input pos=1 text=b t=300\n"
        )

        self.assertEqual(len(engine.stack), 2)
        self.assertEqual(engine.redo_groups, [])

    def test_new_edit_truncates_redo_but_caret_does_not(self):
        lines = [
            f"input pos={index} text=a t={index * 10}"
            for index in range(9)
        ]
        engine = run(
            "\n".join(lines)
            + "\nundo t=1000\n"
            "caret pos=2 t=1100\n"
            "input pos=2 text=z t=1200\n"
            "redo t=1300\n"
        )

        self.assertEqual(engine.redo_groups, [])
        self.assertEqual(engine.text, "aazaaaa")
        self.assertEqual(engine.cursor, 3)

    def test_stack_is_capped_at_eight_entries(self):
        lines = [f"input pos={index} text=a t={index * 1000}" for index in range(9)]
        engine = run("\n".join(lines))

        self.assertEqual(len(engine.stack), 8)
        self.assertEqual([entry.id for entry in engine.stack], list(range(2, 10)))


class ParserTest(unittest.TestCase):
    def test_ignores_blank_lines_and_comments(self):
        parsed = parse_script("# comment\n\ninput pos=0 text=a t=0\n")

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].text, "a")

    def test_rejects_decreasing_timestamp(self):
        with self.assertRaises(ValueError):
            parse_script("input pos=0 text=a t=10\ninput pos=1 text=b t=9\n")


if __name__ == "__main__":
    unittest.main()
