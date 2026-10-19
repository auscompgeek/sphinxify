import pytest
from docutils import nodes
from docutils.core import publish_doctree

import sphinxify
import sphinxify.from_java


def literal_blocks(text):
    tree = publish_doctree(text, settings_overrides={"halt_level": 2})
    assert not list(tree.findall(nodes.system_message))
    return list(tree.findall(nodes.literal_block))


@pytest.mark.parametrize(
    "convert",
    [
        sphinxify.Doc.from_comment,
        sphinxify.process_doc,
        sphinxify.from_java.process_raw,
    ],
)
def test_entry_points_forward_callback(convert):
    seen = []

    def transform(block):
        seen.append(block)
        return sphinxify.CodeBlockReplacement("timer.start()", "python")

    result = str(
        convert(
            "/** Before\n * @code{.cpp}\n * timer.Start();\n * @endcode\n * After\n */",
            code_block_transform=transform,
        )
    )
    assert len(seen) == 1
    assert (seen[0].text, seen[0].language, seen[0].index) == (
        "timer.Start();",
        "cpp",
        0,
    )
    assert result == "Before\n\n.. code-block:: python\n\n   timer.start()\n\nAfter"


@pytest.mark.parametrize(
    "opening, closing, directive",
    [
        ("@code", "@endcode", "::"),
        ("<pre><code>", "</code></pre>", "::"),
        (r"\code{.cpp}", r"\endcode", ".. code-block:: cpp"),
        ("```cpp", "```", ".. code-block:: cpp"),
    ],
)
def test_none_preserves_block(opening, closing, directive):
    result = sphinxify.process_doc(
        "Before\n" + opening + "\nif (x) {\n  f();\n}\n" + closing + "\nAfter",
        code_block_transform=lambda b: None,
    )
    assert directive in result
    assert [b.astext() for b in literal_blocks(result)] == ["if (x) {\n  f();\n}"]


@pytest.mark.parametrize(
    "comment",
    [
        "/**\n *\tusing operator(): @code\n *\t\tmeter_t m(5.0);\n *\t\tdouble val = m(); @endcode\n */",
        r"/** Shortcut for\code *this = other.other.triangularView<(*this)::Mode>() \endcode */",
    ],
)
def test_repository_comment_substitution(comment):
    rendered = sphinxify.process_doc(
        comment,
        code_block_transform=lambda block: sphinxify.CodeBlockReplacement(
            "value = example()", "python"
        ),
    )
    assert [b.astext() for b in literal_blocks(rendered)] == ["value = example()"]
    assert "*" not in rendered


@pytest.mark.parametrize("code", ["<pre>", "<pre><code>", r"\code", "@code"])
def test_inline_code_with_block_markers(code):
    assert sphinxify.process_doc("Use {@code " + code + "} here") == (
        "Use ``" + code + "`` here"
    )


@pytest.mark.parametrize("prefix", ["///", "//!"])
def test_literal_comment_reaches_callback_unchanged(prefix):
    code = prefix + " documentation comment"
    seen = []
    result = sphinxify.process_doc(
        "@code\n" + code + "\n@endcode", code_block_transform=seen.append
    )
    assert seen == [sphinxify.CodeBlock(code, None, "doxygen", 0)]
    assert result == "::\n\n   " + code


def test_positional_method_name_callback():
    doc = sphinxify.Doc.from_comment("/** See {@link #Run()} */", str.lower)
    assert doc.desc == "See :meth:`.run`"


def test_blocks_in_all_sections():
    comment = """/**
 * Description.
 * @code
 * desc();
 * @endcode
 * @param x Parameter.
 *
 * @code
 * param();
 * @endcode
 * @return Result.
 *
 * @code
 * result();
 * @endcode
 * @deprecated Use something else.
 *
 * @code
 * deprecated();
 * @endcode
 */"""
    seen = []

    def transform(block):
        seen.append(block.text)
        return sphinxify.CodeBlockReplacement(f"example_{block.index}()", "python")

    doc = sphinxify.Doc.from_comment(comment, code_block_transform=transform)
    assert seen == ["desc();", "param();", "result();", "deprecated();"]
    assert str(doc) == (
        "Description.\n\n.. code-block:: python\n\n   example_0()\n\n"
        ":deprecated: Use something else.\n"
        "             \n"
        "             .. code-block:: python\n"
        "             \n"
        "                example_3()\n\n"
        ":param x: Parameter.\n"
        "          \n"
        "          .. code-block:: python\n"
        "          \n"
        "             example_1()\n\n"
        ":returns: Result.\n"
        "          \n"
        "          .. code-block:: python\n"
        "          \n"
        "             example_2()"
    )


def test_note_block_indentation():
    doc = sphinxify.process_doc(
        """/**
 * @note An example.
 *
 * @code{.cpp}
 * f();
 * @endcode
 *
 * Outside the note.
 */""",
        code_block_transform=lambda b: sphinxify.CodeBlockReplacement("f()", "python"),
    )
    assert doc == (
        ".. note:: An example.\n\n"
        "   .. code-block:: python\n\n"
        "      f()\n\n"
        "Outside the note."
    )


@pytest.mark.parametrize(
    "prefix", ["Description.", "@param x Value.", "@return Value.", "@deprecated Old."]
)
def test_code_blank_lines_remain_literal(prefix):
    code = 'if x:\n    print("<b>", "@param x", "\\\\", "x_y")\n\n\n    x_y = 1'
    doc = sphinxify.process_doc(
        prefix + "\n@code\nx();\n@endcode",
        code_block_transform=lambda b: sphinxify.CodeBlockReplacement(code, "python"),
    )
    assert literal_blocks(doc)[0].astext() == code


@pytest.mark.parametrize("section", ["@note An example.", "@param x An example."])
@pytest.mark.parametrize(
    "opening,closing",
    [("```cpp", "```"), ("~~~cpp", "~~~"), ("@code{.cpp}", "@endcode")],
)
@pytest.mark.parametrize("trailing", ["", "   ", "\t"])
def test_block_followed_by_outside_prose(section, opening, closing, trailing):
    doc = sphinxify.process_doc(
        section
        + "\n\n"
        + opening
        + "\nf();\n"
        + closing
        + trailing
        + "\n\nOutside prose."
    )
    tree = publish_doctree(doc, settings_overrides={"halt_level": 2})
    paragraphs = [
        p for p in tree.findall(nodes.paragraph) if p.astext() == "Outside prose."
    ]
    assert len(paragraphs) == 1
    assert isinstance(paragraphs[0].parent, nodes.document)


def test_inline_block_surrounding_prose():
    doc = sphinxify.process_doc(
        "/** Before @code int x; @endcode After */",
        code_block_transform=lambda b: sphinxify.CodeBlockReplacement(
            "x = 1", "python"
        ),
    )
    assert doc == "Before\n\n.. code-block:: python\n\n   x = 1\n\nAfter"
