"""Recognition of literal blocks, independent of prose conversion and rendering."""

import re
import textwrap
from dataclasses import dataclass
from typing import Callable, List, Optional, Union


@dataclass(frozen=True)
class CodeBlock:
    """A source block in a comment (index is zero-based source order)."""

    text: str
    language: Optional[str]
    kind: str
    index: int


@dataclass(frozen=True)
class CodeBlockReplacement:
    """Literal replacement text and its optional syntax-highlighting language."""

    text: str
    language: Optional[str] = None


CodeBlockTransform = Callable[[CodeBlock], Optional[CodeBlockReplacement]]

_OPEN = re.compile(
    r"(?P<doxygen>(?<![\w{])[@\\]code\b(?:\{(?P<doxygen_lang>[^}\n]*)\})?)"
    r"|(?P<pre><pre>[ \t\r\n]*(?P<html_code><code>)?)"
    r"|(?P<fence>^[ \t]*(?P<ticks>`{3,}|~{3,})(?P<fence_lang>[^\n]*)\n)",
    re.MULTILINE,
)


def _uncomment(txt: str) -> str:
    """Remove delimiters at comment boundaries, never inside literal content."""
    txt = txt.strip()
    block_comment = txt.startswith("/*")
    if block_comment:
        txt = re.sub(r"^/\*[*!]?<? ?", "", txt, count=1)
        if txt.endswith("*/"):
            txt = txt[:-2]

    lines = []
    for line in txt.splitlines():
        if block_comment:
            line = re.sub(r"^[ \t]*\*(?:<)?(?: |$)", "", line)
        else:
            line = re.sub(r"^[ \t]*(?:///|//!)<?(?: |$)", "", line)
        lines.append(line)
    return textwrap.dedent("\n".join(lines))


def split_comment(txt: str) -> List[Union[str, CodeBlock]]:
    """Split a comment into prose and buffered blocks, preserving source order.

    Raises ValueError for unterminated recognized blocks. Markup inside a block
    is literal, except for that block's closing delimiter.
    """
    txt = _uncomment(txt)
    result: List[Union[str, CodeBlock]] = []
    pos = index = 0
    while True:
        opening = _OPEN.search(txt, pos)
        if opening is None:
            if pos < len(txt):
                result.append(txt[pos:])
            return result
        if opening.start() > pos:
            result.append(txt[pos : opening.start()])

        language = None
        if opening.group("doxygen"):
            kind = "doxygen"
            language = opening.group("doxygen_lang")
            end = re.compile(r"[@\\]endcode\b")
        elif opening.group("pre"):
            kind = "pre"
            end = re.compile(
                r"</code>\s*</pre>" if opening.group("html_code") else r"</pre>"
            )
        else:
            kind = "fence"
            language = opening.group("fence_lang").strip()
            ticks = opening.group("ticks")
            end = re.compile(
                r"^[ \t]*"
                + re.escape(ticks[0])
                + "{"
                + str(len(ticks))
                + r",}[ \t]*(?:\n|$)",
                re.MULTILINE,
            )

        closing = end.search(txt, opening.end())
        if closing is None:
            raise ValueError("Unterminated {} code block {}".format(kind, index))
        if language:
            language = language.strip().lstrip(".") or None
        text = textwrap.dedent(
            txt[opening.end() : closing.start()].strip("\r\n")
        ).strip()
        result.append(CodeBlock(text, language or None, kind, index))
        index += 1
        pos = closing.end()
