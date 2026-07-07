import json

from dictation.glossary import learn_word, load_glossary


def test_learn_word_creates_glossary_and_persists_user_term(tmp_path):
    glossary_path = tmp_path / "glossary.json"

    glossary = learn_word(glossary_path, "  Qwen Turbo  ")

    assert glossary.user_terms == ("Qwen Turbo",)
    saved = json.loads(glossary_path.read_text(encoding="utf-8"))
    assert saved["user_terms"] == ["Qwen Turbo"]
    assert saved["protected_terms"] == []
    assert saved["replacements"] == {}


def test_learn_word_preserves_existing_glossary_data_and_dedupes_case_insensitively(tmp_path):
    glossary_path = tmp_path / "glossary.json"
    glossary_path.write_text(
        json.dumps(
            {
                "user_terms": ["VoiceTray"],
                "protected_terms": ["ACME-123"],
                "replacements": {"codex": "Codex"},
            }
        ),
        encoding="utf-8",
    )

    glossary = learn_word(glossary_path, "voicetray")

    assert glossary.user_terms == ("VoiceTray",)
    assert glossary.protected_terms == ("ACME-123",)
    assert glossary.replacements == (("codex", "Codex"),)
    saved = json.loads(glossary_path.read_text(encoding="utf-8"))
    assert saved == {
        "user_terms": ["VoiceTray"],
        "protected_terms": ["ACME-123"],
        "replacements": {"codex": "Codex"},
    }


def test_learn_word_ignores_blank_terms_without_touching_file(tmp_path):
    glossary_path = tmp_path / "glossary.json"
    glossary_path.write_text(
        json.dumps({"user_terms": ["VoiceTray"], "protected_terms": [], "replacements": {}}),
        encoding="utf-8",
    )

    glossary = learn_word(glossary_path, "   ")

    assert glossary.user_terms == ("VoiceTray",)
    assert load_glossary(glossary_path).user_terms == ("VoiceTray",)

