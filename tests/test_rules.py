from dictation.rules import (
    RuleOptions,
    apply_rules,
    apply_self_corrections,
    maybe_format_list,
    remove_repetitions,
)


def test_repetition_cleanup_words():
    assert remove_repetitions("hello hello world") == "hello world"


def test_self_correction_keeps_final_intent():
    assert apply_self_corrections("send it to John no sorry send it to Jane") == "send it to Jane"


def test_list_formatting_bullets():
    out = maybe_format_list("bullet apples bullet bananas")
    assert out == "- Apples\n- Bananas"


def test_aggressive_removes_like_filler():
    opts = RuleOptions(remove_fillers=True, aggressive_fillers=True)
    out = apply_rules("I like this", opts)
    assert "like" not in out.lower()

