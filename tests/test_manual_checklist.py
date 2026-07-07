from pathlib import Path


def test_manual_test_checklist_covers_required_targets():
    path = Path("docs/TEST_CHECKLIST.md")

    assert path.exists()
    text = path.read_text(encoding="utf-8").lower()
    for required in (
        "notepad",
        "vs code",
        "chrome textarea",
        "slack",
        "terminal fallback",
        "rdp focus-change",
    ):
        assert required in text


def test_manual_test_checklist_records_verification_commands():
    text = Path("docs/TEST_CHECKLIST.md").read_text(encoding="utf-8").lower()

    assert "python -b -m pytest tests\\ -q" in text
    assert "python -b -m voicetray.eval" in text
    assert "python -b tools\\soak.py --cycles 50 --target synthetic" in text
