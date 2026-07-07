from pathlib import Path


def test_removed_stt_engines_are_not_referenced_in_runtime_sources():
    root = Path(__file__).resolve().parents[1]
    forbidden_terms = (
        "vo" "sk",
        "recognize_" "google",
        "speech_" "recognition",
        "speech" "recognition",
        "py" "audio",
    )
    text_suffixes = {".bat", ".ini", ".py", ".txt"}
    ignored_parts = {".git", ".pytest_cache", "__pycache__"}

    hits = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in text_suffixes:
            continue
        if ignored_parts.intersection(path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for term in forbidden_terms:
            if term in text:
                hits.append(str(path.relative_to(root)))
                break

    assert hits == []
