from pathlib import Path


def test_legacy_settings_gui_and_saved_text_files_are_removed():
    root = Path(__file__).resolve().parents[1]

    assert not (root / "voicetray_settings_gui.py").exists()
    assert not (root / "saved_texts.txt").exists()
    assert not (root / "voicetray" / "saved_texts.txt").exists()


def test_runtime_sources_do_not_reference_saved_text_file_flow():
    root = Path(__file__).resolve().parents[1]
    forbidden_terms = (
        "saved_texts.txt",
        "save_text_to_file",
        "append_text_history",
        "record_and_save_to_file",
    )
    hits = []
    for path in (root / "voicetray").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for term in forbidden_terms:
            if term in text:
                hits.append(f"{path.relative_to(root)}:{term}")

    assert hits == []


def test_user_docs_do_not_point_to_legacy_saved_text_flow():
    root = Path(__file__).resolve().parents[1]
    forbidden_terms = (
        "saved_texts.txt",
        "save directly to text files",
        "saving it to text files",
    )
    hits = []
    for path in (root / "readme.md", root / "index.html"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        lowered = text.lower()
        for term in forbidden_terms:
            if term in lowered:
                hits.append(f"{path.name}:{term}")

    assert hits == []
