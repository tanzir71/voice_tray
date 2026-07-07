from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from voicetray.dictation import DictationConfig, DictationContext, DictationPipeline
from voicetray.dictation.llm_local import LocalLLMConfig


DEFAULT_CORPUS_PATH = Path(__file__).resolve().parents[1] / "tests" / "eval_corpus.jsonl"
DEFAULT_MIN_PASS_RATE = 90.0


@dataclass(frozen=True)
class EvalCase:
    id: str
    input_text: str
    expected: str
    mode: str
    profile: str


@dataclass(frozen=True)
class EvalFailure:
    case: EvalCase
    actual: str


@dataclass(frozen=True)
class EvalResult:
    total: int
    passed: int
    failures: tuple[EvalFailure, ...]

    @property
    def failed(self) -> int:
        return len(self.failures)

    @property
    def pass_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100.0


def load_eval_corpus(path: str | Path = DEFAULT_CORPUS_PATH) -> list[EvalCase]:
    corpus_path = Path(path)
    cases: list[EvalCase] = []
    with corpus_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            case_id = str(data.get("id") or f"line-{line_number}")
            input_text = str(data["input"])
            expected = str(data["expected"])
            mode = str(data.get("mode", "balanced"))
            profile = str(data.get("profile", "general"))
            cases.append(
                EvalCase(
                    id=case_id,
                    input_text=input_text,
                    expected=expected,
                    mode=mode,
                    profile=profile,
                )
            )
    return cases


def run_eval(
    cases: Iterable[EvalCase],
    pipeline: DictationPipeline | None = None,
) -> EvalResult:
    active_pipeline = pipeline or DictationPipeline(
        DictationConfig(glossary_path="", llm=LocalLLMConfig(enabled=False))
    )
    failures: list[EvalFailure] = []
    total = 0
    passed = 0
    for case in cases:
        total += 1
        context = DictationContext(mode=case.mode, profile=case.profile)
        actual = active_pipeline.process_transcript(case.input_text, context)
        if actual == case.expected:
            passed += 1
        else:
            failures.append(EvalFailure(case=case, actual=actual))
    return EvalResult(total=total, passed=passed, failures=tuple(failures))


def print_result(result: EvalResult) -> None:
    sys.stdout.write(f"Pass rate: {result.pass_rate:.1f}% ({result.passed}/{result.total} passed)\n")
    if not result.failures:
        return
    sys.stdout.write("Failures:\n")
    for failure in result.failures:
        case = failure.case
        sys.stdout.write(f"- {case.id} [{case.mode}/{case.profile}]\n")
        sys.stdout.write(f"  input:    {case.input_text}\n")
        sys.stdout.write(f"  expected: {case.expected}\n")
        sys.stdout.write(f"  actual:   {failure.actual}\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run VoiceTray dictation golden-file evals.")
    parser.add_argument(
        "--corpus",
        default=str(DEFAULT_CORPUS_PATH),
        help="Path to JSONL eval corpus.",
    )
    parser.add_argument(
        "--min-pass-rate",
        type=float,
        default=DEFAULT_MIN_PASS_RATE,
        help="Minimum pass rate percentage required for exit code 0.",
    )
    args = parser.parse_args(argv)

    result = run_eval(load_eval_corpus(args.corpus))
    print_result(result)
    return 0 if result.pass_rate >= args.min_pass_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
