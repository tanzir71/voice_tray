import subprocess
import sys
from pathlib import Path


def test_eval_corpus_has_required_size_and_coverage():
    from voicetray.eval import DEFAULT_CORPUS_PATH, load_eval_corpus

    cases = load_eval_corpus(DEFAULT_CORPUS_PATH)

    assert len(cases) >= 40
    assert {case.mode for case in cases} >= {"raw", "balanced", "aggressive"}
    assert {case.profile for case in cases} >= {"general", "email", "chat", "notes", "code/comments"}
    assert all(case.input_text.strip() for case in cases)
    assert all(case.expected.strip() for case in cases)


def test_eval_harness_default_corpus_meets_ci_target():
    from voicetray.eval import DEFAULT_CORPUS_PATH, DEFAULT_MIN_PASS_RATE, load_eval_corpus, run_eval

    result = run_eval(load_eval_corpus(DEFAULT_CORPUS_PATH))

    assert result.pass_rate >= DEFAULT_MIN_PASS_RATE
    assert result.failed == 0


def test_eval_cli_prints_pass_rate_and_exits_zero():
    root = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [sys.executable, "-m", "voicetray.eval"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Pass rate:" in result.stdout
    assert "passed" in result.stdout

