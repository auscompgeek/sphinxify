"""HTML conversion tests requiring callbacks or case matrices.

Fixed conversion examples live in the html_* input/expected corpus fixtures.
"""

import pytest
from docutils import nodes
from docutils.core import publish_doctree

from sphinxify import CodeBlockReplacement, Doc, process_doc


@pytest.mark.parametrize(
    "prefix, expected",
    [
        (
            "@param values Available values:",
            "\n\n:param values: Available values:\n"
            "               \n"
            "               .. list-table::\n"
            "               \n"
            "                  * - one\n"
            "                    - 1",
        ),
        (
            "@return Available values:",
            "\n\n:returns: Available values:\n"
            "          \n"
            "          .. list-table::\n"
            "          \n"
            "             * - one\n"
            "               - 1",
        ),
        (
            "@deprecated Available values:",
            "\n\n:deprecated: Available values:\n"
            "             \n"
            "             .. list-table::\n"
            "             \n"
            "                * - one\n"
            "                  - 1",
        ),
    ],
)
def test_table_in_fields(prefix, expected):
    assert (
        process_doc(prefix + "\n<table>\n<tr><td>one</td><td>1</td></tr>\n</table>")
        == expected
    )


@pytest.mark.parametrize(
    "tag, prefix, expected",
    [
        ("ul", "", "- Before\n\n  ::\n\n     code\n\n  After\n- Next"),
        ("ol", "", "#. Before\n\n   ::\n\n      code\n\n   After\n#. Next"),
        (
            "ul",
            "@note ",
            ".. note::\n\n   - Before\n\n     ::\n\n        code\n\n     After\n   - Next",
        ),
        (
            "ol",
            "@note ",
            ".. note::\n\n   #. Before\n\n      ::\n\n         code\n\n      After\n   #. Next",
        ),
    ],
)
def test_literal_stays_inside_html_list(tag, prefix, expected):
    assert (
        process_doc(
            prefix + f"<{tag}><li>Before<pre>code</pre>After</li>"
            f"<li>Next</li></{tag}>"
        )
        == expected
    )


@pytest.mark.parametrize(
    "tag, expected",
    [
        ("ul", ".. note::\n\n   - First\n     continued"),
        ("ol", ".. note::\n\n   #. First\n      continued"),
    ],
)
def test_wrapped_list_item_in_note_is_one_paragraph(tag, expected):
    assert process_doc(f"@note <{tag}><li>First\ncontinued</li></{tag}>") == expected


@pytest.mark.parametrize("transformed", [False, True])
@pytest.mark.parametrize(
    "before, after, expected",
    [
        (
            "",
            "",
            '::\n\n   x = """first  \n   second"""\n   print(x) \t',
        ),
        (
            "<ul><li>Example",
            "</li></ul>",
            '- Example\n\n  ::\n\n     x = """first  \n     second"""\n     print(x) \t',
        ),
        (
            "@param x Example\n",
            "",
            "\n\n:param x: Example\n"
            "          \n"
            "          ::\n"
            "          \n"
            '             x = """first  \n'
            '             second"""\n'
            "             print(x) \t",
        ),
    ],
)
def test_literal_trailing_whitespace_is_preserved(transformed, before, after, expected):
    code = 'x = """first  \nsecond"""\nprint(x) \t'
    kwargs = {}
    if transformed:
        kwargs["code_block_transform"] = lambda block: CodeBlockReplacement(code)
    source = "original" if transformed else code
    assert (
        process_doc(before + "<pre>" + source + "</pre>" + after, **kwargs) == expected
    )


def test_table_in_note():
    assert (
        process_doc(
            "@note Allocations:\n<table><tr><td>one</td><td>1</td></tr></table>"
        )
        == ".. note:: Allocations:\n   \n\n   .. list-table::\n\n      * - one\n        - 1"
    )


@pytest.mark.parametrize(
    "html",
    [
        '<table><tr><td colspan="2">merged</td></tr></table>',
        "<table><tr><td><table><tr><td>nested</td></tr></table></td></tr></table>",
        "<table><tr><td>unfinished",
        "<table></table>",
        "<table><tr><th>Only header</th></tr></table>",
        "<table><thead><tr><th>First</th></tr><tr><th>Second</th></tr></thead></table>",
        "<table>lost<tr><td>kept</td></tr></table>",
        "<table><tr>lost<td>kept</td></tr></table>",
        "<table><p>lost</p><tr><td>kept</td></tr></table>",
        "<table><tr><td>one</td></tr><tr><td>two</td><td>three</td></tr></table>",
    ],
)
def test_unsupported_tables_preserve_content(html):
    assert process_doc(html) == html


@pytest.mark.parametrize("tag", ["code", "tt", "CODE", "TT"])
@pytest.mark.parametrize(
    "content, expected",
    [
        ("value_", r"Use ``value_`` with prose\_."),
        ("value_\nother_", r"Use ``value_ other_`` with prose\_."),
        (r"value\_", r"Use ``value\_`` with prose\_."),
        ("value_ &amp; other_", r"Use ``value_ & other_`` with prose\_."),
    ],
)
def test_html_code_preserves_underscores(tag, content, expected):
    assert (
        process_doc(f'Use <{tag} class="identifier">{content}</{tag}> with prose_.')
        == expected
    )


@pytest.mark.parametrize("tag", ["strong", "em", "b", "i"])
@pytest.mark.parametrize(
    "template, expected",
    [
        (
            '<{tag}><a href="https://example.com">API reference</a></{tag}>',
            "`API reference <https://example.com>`__",
        ),
        (
            'pre<{tag}><a href="https://example.com">API reference</a></{tag}>post',
            r"pre\ `API reference <https://example.com>`__\ post",
        ),
        (
            '<{tag}>See <em><a href="https://example.com">API reference</a></em> now.</{tag}>',
            "See `API reference <https://example.com>`__ now.",
        ),
    ],
)
def test_emphasis_wrapped_links_remain_references(tag, template, expected):
    result = process_doc(template.format(tag=tag))
    assert result == expected
    # A warning-free parse alone misses hyperlinks swallowed by emphasis.
    tree = publish_doctree(result, settings_overrides={"halt_level": 2})
    references = list(tree.findall(nodes.reference))
    assert len(references) == 1
    assert references[0].astext() == "API reference"
    assert references[0]["refuri"] == "https://example.com"


@pytest.mark.parametrize("tag", ["strong", "em", "b", "i"])
@pytest.mark.parametrize("code_tag", ["code", "tt"])
def test_emphasis_wrapped_code_remains_literal(tag, code_tag):
    result = process_doc(f"<{tag}><{code_tag}>foo</{code_tag}></{tag}>")
    assert result == "``foo``"
    tree = publish_doctree(result, settings_overrides={"halt_level": 2})
    assert [literal.astext() for literal in tree.findall(nodes.literal)] == ["foo"]


@pytest.mark.parametrize("code_tag", ["code", "tt"])
def test_nested_emphasis_wrapped_code_keeps_boundaries(code_tag):
    assert (
        process_doc(f"pre<strong><em><{code_tag}>foo</{code_tag}></em></strong>post")
        == r"pre\ ``foo``\ post"
    )


def test_code_block_callback_between_definition_entries():
    result = process_doc(
        "<dl><dt>Term</dt><dd>Definition</dd><pre>original</pre>"
        "<dt>Next</dt><dd>Other</dd></dl>",
        code_block_transform=lambda block: CodeBlockReplacement(
            'print("<T>&amp;")', "python"
        ),
    )
    assert result == (
        "Term\n   Definition\n\n.. code-block:: python\n\n"
        '   print("<T>&amp;")\n\nNext\n   Other'
    )


def test_code_block_callback_between_list_items():
    result = process_doc(
        "<ul><li>before</li><pre>original</pre><li>after</li></ul>",
        code_block_transform=lambda block: CodeBlockReplacement(
            'print("<T>&amp;")', "python"
        ),
    )
    assert result == (
        "- before\n\n.. code-block:: python\n\n" '   print("<T>&amp;")\n\n- after'
    )


def test_html_and_code_block_callback_coexist():
    seen = []

    def transform(block):
        seen.append(block.text)
        return CodeBlockReplacement('print("<table>&amp;</table>")', "python")

    result = process_doc(
        """<p>Example with <code>normalizeKey</code>:</p>
<pre><code>
normalizeKey("/foo/bar", true) == "/foo/bar"
</code></pre>
<table><tr><td>After</td></tr></table>""",
        code_block_transform=transform,
    )
    assert seen == ['normalizeKey("/foo/bar", true) == "/foo/bar"']
    assert result == (
        "Example with ``normalizeKey``:\n\n"
        ".. code-block:: python\n\n"
        '   print("<table>&amp;</table>")\n\n'
        ".. list-table::\n\n"
        "   * - After"
    )


@pytest.mark.parametrize(
    "in_table, expected",
    [
        (False, "Dense versus sparse:\n   This Matrix handles dense matrices."),
        (
            True,
            ".. list-table::\n\n   * - Dense versus sparse:\n"
            "          This Matrix handles dense matrices.",
        ),
    ],
)
def test_eigen_definition_list(in_table, expected):
    html = "<dl>\n<dt>Dense versus sparse:</dt>\n<dd>This Matrix handles dense matrices.</dd>\n</dl>"
    if in_table:
        html = "<table><tr><td>" + html + "</td></tr></table>"
    assert process_doc(html) == expected


def test_cell_method_callback():
    doc = Doc.from_comment("<table><tr><td>{@link #Run()}</td></tr></table>", str.lower)
    assert doc.desc == ".. list-table::\n\n   * - :meth:`.run`"
