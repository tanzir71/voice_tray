import pytest

from dictation.rules import (
    RuleOptions,
    apply_rules,
    apply_self_corrections,
    maybe_format_list,
    remove_fillers,
    remove_repetitions,
)


def test_repetition_cleanup_words():
    assert remove_repetitions("hello hello world") == "hello world"


def test_self_correction_keeps_final_intent():
    assert apply_self_corrections("send it to John no sorry send it to Jane") == "send it to Jane"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("set the meeting for two actually three", "set the meeting for three"),
        ("set the meeting for two actually for three", "set the meeting for three"),
        ("send it to John actually Jane", "send it to Jane"),
        ("send it to John actually to Jane", "send it to Jane"),
        ("make it red no wait blue", "make it blue"),
        ("make it red no wait make it blue", "make it blue"),
        ("the deadline is Monday I mean Tuesday", "the deadline is Tuesday"),
        ("the deadline is on Monday I mean on Tuesday", "the deadline is on Tuesday"),
        ("book it tomorrow morning sorry Friday afternoon", "book it Friday afternoon"),
        ("book it for tomorrow morning sorry for Friday afternoon", "book it for Friday afternoon"),
        ("bring apples scratch that oranges", "bring oranges"),
        ("bring apples and pears scratch that oranges and bananas", "bring oranges and bananas"),
        ("call John Smith no sorry Jane Doe", "call Jane Doe"),
        ("use the beta endpoint actually the production endpoint", "use the production endpoint"),
        ("the total is twenty five no actually thirty five", "the total is thirty five"),
        ("please add a comma no wait a semicolon", "please add a semicolon"),
        ("move the meeting to Friday at two actually Monday at three", "move the meeting to Monday at three"),
        ("tell Sam I mean tell Priya", "tell Priya"),
        ("turn left at Pine Street actually Oak Avenue", "turn left at Oak Avenue"),
        ("set priority high sorry low", "set priority low"),
    ],
)
def test_self_correction_replaces_immediately_preceding_phrase(raw, expected):
    assert apply_self_corrections(raw) == expected


@pytest.mark.parametrize(
    "text",
    [
        "no, wait for me at the lobby",
        "sorry is the hardest word",
        "I mean it when I say thanks",
        "actually this is already correct",
        "scratch that itch before it gets worse",
        "there is no wait time today",
        "no wait list is available",
        "she said sorry and left",
        "what I mean is we can ship it",
        "the word actually appears in this sentence",
    ],
)
def test_self_correction_ignores_false_positive_cues(text):
    assert apply_self_corrections(text) == text


def test_list_formatting_bullets():
    out = maybe_format_list("bullet apples bullet bananas")
    assert out == "- Apples\n- Bananas"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("one apples two bananas three carrots", "1. Apples\n2. Bananas\n3. Carrots"),
        ("number one apples number two bananas", "1. Apples\n2. Bananas"),
        ("first apples second bananas third carrots", "1. Apples\n2. Bananas\n3. Carrots"),
        ("1 apples 2 bananas 3 carrots", "1. Apples\n2. Bananas\n3. Carrots"),
    ],
)
def test_list_formatting_numbered_enumerations(raw, expected):
    assert maybe_format_list(raw) == expected


def test_list_formatting_bullet_point_phrasing():
    assert maybe_format_list("bullet point apples bullet point bananas") == "- Apples\n- Bananas"


def test_new_paragraph_spoken_marker_preserves_paragraph_break():
    opts = RuleOptions(
        remove_fillers=False,
        remove_repetitions=False,
        handle_self_corrections=False,
        normalize_punctuation=True,
        normalize_capitalization=True,
        convert_spoken_punctuation=False,
        convert_spoken_newlines=True,
    )

    assert apply_rules("opening thought new paragraph next thought", opts) == (
        "Opening thought\n\nNext thought"
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("um ah uhm hello", "hello"),
        ("hmm erm we can ship", "we can ship"),
        ("mm mmm this is ready", "this is ready"),
    ],
)
def test_conservative_filler_cleanup_expands_high_confidence_vocal_fillers(raw, expected):
    assert remove_fillers(raw, aggressive=False) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("like I think we can ship", "I think we can ship"),
        ("you know we should ship this", "we should ship this"),
        ("I sort of think this works", "I think this works"),
        ("it is kind of maybe ready", "it is maybe ready"),
        ("this is basically ready", "this is ready"),
    ],
)
def test_aggressive_filler_cleanup_removes_ambiguous_discourse_fillers(raw, expected):
    assert remove_fillers(raw, aggressive=True) == expected


@pytest.mark.parametrize(
    "text",
    [
        "I like this design",
        "you know the answer",
        "a sort of apple",
        "this kind of problem",
    ],
)
def test_aggressive_filler_cleanup_keeps_likely_semantic_uses(text):
    assert remove_fillers(text, aggressive=True) == text


def test_balanced_mode_removes_high_confidence_fillers_but_keeps_ambiguous_words():
    opts = RuleOptions(remove_fillers=True, aggressive_fillers=False)

    assert apply_rules("um this is like a good idea", opts) == "This is like a good idea"

