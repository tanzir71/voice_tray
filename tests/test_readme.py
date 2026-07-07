from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "readme.md"
PILL_GIF = ROOT / "assets" / "readme" / "pill-preview.gif"


def readme_text():
    return README.read_text(encoding="utf-8")


def test_readme_positions_voicetray_against_cloud_competitors():
    text = readme_text()

    assert "Wispr Flow magic, 100% offline and free" in text
    assert "| Capability | Wispr Flow | Typeless | VoiceTray |" in text
    assert "| Privacy | Cloud dictation | Cloud dictation | 100% offline |" in text
    assert "| Price | $15/mo | $12/mo | Free, open source |" in text


def test_readme_embeds_real_pill_preview_gif():
    text = readme_text()

    assert "![VoiceTray dictation pill](assets/readme/pill-preview.gif)" in text
    assert PILL_GIF.exists()
    assert PILL_GIF.read_bytes().startswith((b"GIF87a", b"GIF89a"))


def test_readme_documents_local_model_size_guidance():
    text = readme_text()

    for phrase in (
        "base (~145 MB)",
        "small (better accuracy)",
        "medium (best CPU-viable accuracy)",
        "int8",
        "Qwen2.5-1.5B-Instruct",
        "Q4_K_M",
        "~1 GB",
    ):
        assert phrase in text
