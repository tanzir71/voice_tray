from dictation.llm_local import build_cleanup_prompt


def test_cleanup_prompt_includes_tone_hint_and_strict_json_contract():
    prompt = build_cleanup_prompt("hello world", tone_hint="formal")

    assert "Tone hint: formal" in prompt
    assert "Return JSON only" in prompt
    assert "TRANSCRIPT:\nhello world" in prompt

