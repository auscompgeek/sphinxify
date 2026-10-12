import pytest

from sphinxify._codeblocks import CodeBlock, split_comment


@pytest.mark.parametrize(
    "opening,closing,language,kind",
    [
        ("@code", "@endcode", None, "doxygen"),
        (r"\code", r"\endcode", None, "doxygen"),
        ("@code{.cpp}", "@endcode", "cpp", "doxygen"),
        (r"\code{.cpp}", r"\endcode", "cpp", "doxygen"),
        ("<pre>", "</pre>", None, "pre"),
        ("<pre><code>", "</code></pre>", None, "pre"),
        ("```cpp", "```", "cpp", "fence"),
        ("~~~", "~~~", None, "fence"),
    ],
)
def test_block_forms(opening, closing, language, kind):
    chunks = split_comment(
        "/**\n * Before\n * "
        + opening
        + "\n * if (x) {\n *   f();\n * }\n * "
        + closing
        + "\n * After\n */"
    )
    assert len(chunks) == 3
    assert chunks[0].strip() == "Before"
    assert chunks[1] == CodeBlock("if (x) {\n  f();\n}", language, kind, 0)
    assert chunks[2].strip() == "After"


def test_inline_block_surrounding_prose():
    chunks = split_comment("/** Before @code{.cpp} int x; @endcode After */")
    assert chunks[0].strip() == "Before"
    assert chunks[1] == CodeBlock("int x;", "cpp", "doxygen", 0)
    assert chunks[2].strip() == "After"


def test_multiple_inline_blocks():
    chunks = split_comment("Before <pre>a();</pre> between @code b(); @endcode after")
    blocks = [c for c in chunks if isinstance(c, CodeBlock)]
    assert blocks == [
        CodeBlock("a();", None, "pre", 0),
        CodeBlock("b();", None, "doxygen", 1),
    ]
    assert "between" in chunks[2]


def test_inline_javadoc_is_not_a_block():
    assert split_comment("Use {@code x} here") == ["Use {@code x} here"]


@pytest.mark.parametrize(
    "opening,decoration,closing",
    [
        ("/**\n", " * ", "\n */"),
        ("/*!\n", " * ", "\n */"),
        ("*\n", "* ", "\n*/"),
        ("", "/// ", ""),
        ("", "//! ", ""),
        ("", "", ""),
    ],
)
def test_comment_decoration(opening, decoration, closing):
    content = "\n".join(
        decoration + s for s in ["@code", "if (x) {", "  f();", "}", "@endcode"]
    )
    blocks = [
        c
        for c in split_comment(opening + content + closing)
        if isinstance(c, CodeBlock)
    ]
    assert blocks[0].text == "if (x) {\n  f();\n}"


def test_literal_markup_in_block():
    code = 'if x:\n    print("<b>", "@param x", "/* */", "\\\\")\n\n\n    # @code\n    x_y = 1'
    chunks = split_comment(
        "/// ```python\n"
        + "\n".join("/// " + s for s in code.split("\n"))
        + "\n/// ```"
    )
    assert [c.text for c in chunks if isinstance(c, CodeBlock)] == [code]


def test_long_fence_contains_short_fence():
    chunks = split_comment("````text\n```\n~~~\ninside\n`````\nAfter")
    assert chunks[0] == CodeBlock("```\n~~~\ninside", "text", "fence", 0)
    assert chunks[1].strip() == "After"


@pytest.mark.parametrize(
    "txt,kind",
    [
        ("@code\nx", "doxygen"),
        ("<pre>x", "pre"),
        ("<pre><code>x</pre>", "pre"),
        ("```cpp\nx\n~~~", "fence"),
        ("````cpp\nx\n```", "fence"),
    ],
)
def test_unterminated_block(txt, kind):
    with pytest.raises(ValueError, match=kind + r".*0"):
        split_comment(txt)
