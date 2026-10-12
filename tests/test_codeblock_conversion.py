import pytest
from docutils import nodes
from docutils.core import publish_doctree

import sphinxify


def literal_blocks(text):
    tree = publish_doctree(text, settings_overrides={"halt_level": 2})
    assert not list(tree.findall(nodes.system_message))
    return list(tree.findall(nodes.literal_block))


@pytest.mark.parametrize(
    "convert",
    [sphinxify.Doc.from_comment, sphinxify.process_doc, sphinxify.process_raw],
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
    assert "timer.Start" not in result
    assert result.startswith("Before\n") and result.endswith("After")
    assert ".. code-block:: python" in result
    assert [b.astext() for b in literal_blocks(result)] == ["timer.start()"]


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


def test_existing_positional_method_name_callback():
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
    blocks = literal_blocks(str(doc))
    assert len(blocks) == 4
    fields = {}
    for b in blocks:
        parent = b.parent
        while parent is not None and not isinstance(parent, nodes.field):
            parent = parent.parent
        fields[parent[0].astext() if parent is not None else "description"] = b.astext()
    assert fields == {
        "description": "example_0()",
        "param x": "example_1()",
        "returns": "example_2()",
        "deprecated": "example_3()",
    }


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
    block = literal_blocks(doc)[0]
    assert isinstance(block.parent, nodes.note)
    assert block.parent.astext() == "An example.\n\nf()"
    assert doc.endswith("Outside the note.")


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
def test_block_followed_by_outside_prose(section, opening, closing):
    doc = sphinxify.process_doc(
        section + "\n\n" + opening + "\nf();\n" + closing + "\n\nOutside prose."
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
    assert literal_blocks(doc)[0].astext() == "x = 1"
    assert doc.startswith("Before\n") and doc.endswith("After")
