def test_soak_run_reports_success_for_stable_rss_and_fast_cycles():
    from tools.soak import run_soak

    rss_values = iter([100_000_000, 104_000_000])
    cycles = []

    result = run_soak(
        cycles=3,
        rss_reader=lambda: next(rss_values),
        cycle_runner=lambda index: cycles.append(index),
        clock=iter([0.0, 0.1, 0.2, 0.3, 0.4, 0.5]).__next__,
        freeze_timeout_seconds=1.0,
    )

    assert cycles == [1, 2, 3]
    assert result.cycles == 3
    assert result.failures == 0
    assert result.ui_freezes == 0
    assert result.rss_growth_ratio == 0.04
    assert result.ok is True


def test_soak_run_fails_when_rss_growth_exceeds_threshold():
    from tools.soak import run_soak

    rss_values = iter([100_000_000, 112_000_000])

    result = run_soak(
        cycles=1,
        rss_reader=lambda: next(rss_values),
        cycle_runner=lambda _index: None,
        max_rss_growth_ratio=0.10,
    )

    assert result.rss_growth_ratio == 0.12
    assert result.ok is False


def test_soak_run_counts_slow_cycles_as_ui_freezes():
    from tools.soak import run_soak

    result = run_soak(
        cycles=1,
        rss_reader=lambda: 100_000_000,
        cycle_runner=lambda _index: None,
        clock=iter([0.0, 2.5]).__next__,
        freeze_timeout_seconds=1.0,
    )

    assert result.ui_freezes == 1
    assert result.ok is False


def test_soak_parser_defaults_to_fifty_synthetic_cycles():
    from tools.soak import build_parser

    args = build_parser().parse_args([])

    assert args.cycles == 50
    assert args.target == "synthetic"
    assert args.max_rss_growth == 0.10


def test_soak_script_runs_by_path():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-B", "tools/soak.py", "--cycles", "1"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "PASS: cycles=1" in result.stdout
