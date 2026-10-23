import pytest

from sphinxify import process_doc


@pytest.mark.parametrize(
    "section, expected",
    [
        (
            "@param x Value.",
            "\n\n:param x: Value.\n          \n          ::\n          \n"
            "             f();\n          \n          Continued.",
        ),
        (
            "@note Value.",
            ".. note:: Value.\n\n   ::\n\n      f();\n\n   Continued.",
        ),
    ],
)
@pytest.mark.parametrize(
    "opening, closing",
    [("@code", "@endcode"), ("<pre>", "</pre>"), ("<pre><code>", "</code></pre>")],
)
@pytest.mark.parametrize("trailing", ["   ", "\t"])
def test_closing_marker_whitespace_preserves_section(
    section, expected, opening, closing, trailing
):
    assert (
        process_doc(f"{section}\n{opening}\nf();\n{closing}{trailing}\nContinued.")
        == expected
    )


@pytest.mark.parametrize(
    "section, expected",
    [
        ("@note", ".. note::\n\n   ::\n\n      f();"),
        ("@deprecated", "\n\n:deprecated: ::\n             \n                f();"),
    ],
)
def test_bare_section_before_inline_block(section, expected):
    assert process_doc(f"{section} @code f(); @endcode") == expected


@pytest.mark.parametrize(
    "section, expected",
    [
        (
            "@param x Value.",
            "\n\n:param x: Value.\n          \n          ::\n          \n             f();",
        ),
        ("@note Value.", ".. note:: Value.\n\n   ::\n\n      f();"),
        (
            "@deprecated Value.",
            "\n\n:deprecated: Value.\n             \n             ::\n"
            "             \n                f();",
        ),
    ],
)
@pytest.mark.parametrize("layout", ["\n\n  ", "\n \n  \n\t"])
def test_whitespace_before_block_preserves_section(section, expected, layout):
    assert process_doc(f"{section}{layout}@code\nf();\n  @endcode") == expected
