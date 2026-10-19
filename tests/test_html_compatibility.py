"""HTML/Doxygen interactions requiring API or conversion-output assertions.

Baseline-compatible preservation examples live in compat_* corpus fixtures.
"""

import pytest

from sphinxify import Doc, process_doc


@pytest.mark.parametrize(
    "directive",
    ["@param x", r"\param x", "@return", r"\return", "@deprecated", "@brief"],
)
@pytest.mark.parametrize("closing", ["", "</p>"])
def test_paragraph_prefix_does_not_hide_doxygen_directives(directive, closing):
    plain = Doc.from_comment(directive + " Description")
    html = Doc.from_comment("<p>" + directive + " Description" + closing)
    assert html == plain


@pytest.mark.parametrize(
    "html, expected",
    [
        (
            "<p>This is important.</p>\nMore explanation.",
            ".. note::\n\n   This is important.\n\n   More explanation.",
        ),
        (
            "<p>This is important.</p> More explanation.",
            ".. note::\n\n   This is important.\n\n   More explanation.",
        ),
        (
            "<p>This is important.\nMore explanation.</p>",
            ".. note::\n\n   This is important.\n   More explanation.",
        ),
        (
            "<ul><li>This is important.<li>More explanation.</ul>",
            ".. note::\n\n   - This is important.\n\n   - More explanation.",
        ),
    ],
)
def test_html_stays_inside_note(html, expected):
    assert process_doc("@note " + html) == expected


@pytest.mark.parametrize(
    "html, expected",
    [
        (
            "<p>One</p><p>Two</p>",
            ".. note:: Intro\n   \n\n   One\n\n   Two",
        ),
        (
            "<p>One</p> <p>Two</p><ul><li>Three</li></ul>",
            ".. note:: Intro\n   \n\n   One\n\n   Two\n\n   - Three",
        ),
        (
            "<p>One</p><p>Two</p>\n\n<p>Outside</p><p>Still outside</p>",
            ".. note:: Intro\n   \n\n   One\n\n   Two\n\nOutside\n\nStill outside",
        ),
    ],
)
def test_adjacent_html_blocks_keep_source_line_note_indentation(html, expected):
    assert process_doc("@note Intro\n" + html) == expected


@pytest.mark.parametrize("separator", ["", " "])
@pytest.mark.parametrize(
    "inline, expected",
    [
        (
            "<code>value</code>",
            ".. note::\n\n   First\n\n   ``value`` is important.",
        ),
        (
            '<a href="https://example.com">value</a>',
            ".. note::\n\n   First\n\n   `value <https://example.com>`__ is important.",
        ),
    ],
)
def test_inline_after_note_paragraph_keeps_indentation(separator, inline, expected):
    assert process_doc(
        "@note <p>First</p>" + separator + inline + " is important."
    ) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        (
            "@note Intro\n<br>next\nmore",
            ".. note:: Intro\n   \n   next\n   more",
        ),
        (
            "@note Intro<br>next\nmore\n\nOutside.<br>Still outside.",
            ".. note:: Intro\n   next\n   more\n\nOutside.\nStill outside.",
        ),
        (
            "@note <p>First</p><br><code>next</code>\nmore",
            ".. note::\n\n   First\n\n   ``next``\n   more",
        ),
        (
            "@note <p>First<br>next\nmore</p>",
            ".. note::\n\n   First\n   next\n   more",
        ),
    ],
)
def test_note_line_break_preserves_indentation(source, expected):
    assert process_doc(source) == expected


def test_inline_after_note_ends_stays_outside():
    assert process_doc(
        "@note <p>First</p>\n\n<code>value</code> is outside."
    ) == ".. note::\n\n   First\n\n``value`` is outside."
