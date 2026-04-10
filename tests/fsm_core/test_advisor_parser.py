import unittest

from src.fsm_core.advisor_parser import (
    AdvisorVerdict,
    ReviseEntryConfig,
    build_revise_register_entry,
    count_revise_rounds,
    parse_advisor_output,
)


class TestParseAdvisorOutput(unittest.TestCase):
    def test_approve_first_line(self) -> None:
        stdout = "APPROVE - all criteria met"
        result = parse_advisor_output(stdout)
        self.assertTrue(result.is_approve)
        self.assertEqual(result.guidance, "")

    def test_approve_with_whitespace(self) -> None:
        stdout = "  APPROVE  \n  some extra text  "
        result = parse_advisor_output(stdout)
        self.assertTrue(result.is_approve)
        self.assertEqual(result.guidance, "")

    def test_revise_with_guidance(self) -> None:
        stdout = "REVISE\nIssue 1: missing docstring\nIssue 2: type hints"
        result = parse_advisor_output(stdout)
        self.assertFalse(result.is_approve)
        self.assertIn("Issue 1", result.guidance)
        self.assertIn("Issue 2", result.guidance)

    def test_revise_single_line(self) -> None:
        stdout = "REVISE"
        result = parse_advisor_output(stdout)
        self.assertFalse(result.is_approve)
        self.assertEqual(result.guidance, "")

    def test_empty_stdout(self) -> None:
        stdout = ""
        result = parse_advisor_output(stdout)
        self.assertFalse(result.is_approve)
        self.assertIn("Unparseable", result.guidance)

    def test_unparseable_output(self) -> None:
        stdout = "INVALID: some garbage"
        result = parse_advisor_output(stdout)
        self.assertFalse(result.is_approve)
        self.assertIn("Unparseable", result.guidance)

    def test_unparseable_truncation(self) -> None:
        long_text = "X" * 300
        result = parse_advisor_output(long_text)
        self.assertFalse(result.is_approve)
        self.assertIn("X" * 100, result.guidance)
        self.assertLess(len(result.guidance), 250)

    def test_revise_with_multiple_lines(self) -> None:
        stdout = "REVISE\nFirst issue\nSecond issue\nThird issue"
        result = parse_advisor_output(stdout)
        self.assertFalse(result.is_approve)
        self.assertIn("First issue", result.guidance)
        self.assertIn("Second issue", result.guidance)
        self.assertIn("Third issue", result.guidance)


class TestCountReviseRounds(unittest.TestCase):
    def test_zero_rounds(self) -> None:
        registers = "— empty —"
        count = count_revise_rounds(registers)
        self.assertEqual(count, 0)

    def test_one_round(self) -> None:
        registers = "REVISE round 1 (nonce abc123): missing docstring"
        count = count_revise_rounds(registers)
        self.assertEqual(count, 1)

    def test_three_rounds(self) -> None:
        registers = (
            "REVISE round 1 (nonce abc123): issue1\n"
            "REVISE round 2 (nonce def456): issue2\n"
            "REVISE round 3 (nonce ghi789): issue3"
        )
        count = count_revise_rounds(registers)
        self.assertEqual(count, 3)

    def test_non_matching_lines(self) -> None:
        registers = (
            "Some random text\n"
            "REVISE round 1 (nonce abc123): issue\n"
            "More text without pattern"
        )
        count = count_revise_rounds(registers)
        self.assertEqual(count, 1)

    def test_partial_pattern_no_match(self) -> None:
        registers = "REVISE round abc (nonce xyz): not a number"
        count = count_revise_rounds(registers)
        self.assertEqual(count, 0)

    def test_multiline_registers(self) -> None:
        registers = (
            "read task file (nonce 7960d0)\n"
            "REVISE round 1 (nonce abc123): issue1\n"
            "REVISE round 2 (nonce def456): issue2\n"
            "some other content"
        )
        count = count_revise_rounds(registers)
        self.assertEqual(count, 2)


class TestBuildReviseRegisterEntry(unittest.TestCase):
    def test_basic_format(self) -> None:
        config = ReviseEntryConfig(round_number=1, nonce="abc123", summary="issue1")
        entry = build_revise_register_entry(config)
        self.assertEqual(entry, "REVISE round 1 (nonce abc123): issue1")

    def test_round_two(self) -> None:
        config = ReviseEntryConfig(round_number=2, nonce="def456", summary="fix issue2")
        entry = build_revise_register_entry(config)
        self.assertEqual(entry, "REVISE round 2 (nonce def456): fix issue2")

    def test_round_three(self) -> None:
        config = ReviseEntryConfig(round_number=3, nonce="ghi789", summary="final issue3")
        entry = build_revise_register_entry(config)
        self.assertEqual(entry, "REVISE round 3 (nonce ghi789): final issue3")

    def test_summary_with_special_chars(self) -> None:
        config = ReviseEntryConfig(
            round_number=1, nonce="xxx", summary="missing: docstring, type hints"
        )
        entry = build_revise_register_entry(config)
        self.assertIn("missing: docstring, type hints", entry)


class TestAdvisorVerdictDataclass(unittest.TestCase):
    def test_approve_verdict(self) -> None:
        verdict = AdvisorVerdict(is_approve=True, guidance="")
        self.assertTrue(verdict.is_approve)
        self.assertEqual(verdict.guidance, "")

    def test_revise_verdict(self) -> None:
        guidance = "Fix these issues"
        verdict = AdvisorVerdict(is_approve=False, guidance=guidance)
        self.assertFalse(verdict.is_approve)
        self.assertEqual(verdict.guidance, guidance)


class TestReviseEntryConfigDataclass(unittest.TestCase):
    def test_config_creation(self) -> None:
        config = ReviseEntryConfig(round_number=1, nonce="abc", summary="test")
        self.assertEqual(config.round_number, 1)
        self.assertEqual(config.nonce, "abc")
        self.assertEqual(config.summary, "test")


if __name__ == "__main__":
    unittest.main()
