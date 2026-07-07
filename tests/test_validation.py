from dictation.validation import validate_llm_output


def test_validation_rejects_changed_urls():
    result = validate_llm_output(
        "visit https://example.com/docs today",
        "visit https://example.org/docs today",
        mode="aggressive",
    )

    assert result.ok is False
    assert result.reason == "urls_changed"


def test_validation_rejects_output_that_is_too_short_by_length_ratio():
    result = validate_llm_output(
        "please send the quarterly planning report to the finance team tomorrow morning",
        "send report",
        mode="aggressive",
    )

    assert result.ok is False
    assert result.reason == "length_ratio"


def test_validation_rejects_output_that_is_too_long_by_length_ratio():
    result = validate_llm_output(
        "send report",
        "send the full detailed quarterly planning report to the finance leadership team tomorrow morning",
        mode="aggressive",
    )

    assert result.ok is False
    assert result.reason == "length_ratio"

