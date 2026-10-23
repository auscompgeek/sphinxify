"""Small HTML fragment renderer for documentation (not a browser layout engine)."""

import re
from dataclasses import dataclass, field
from html import unescape
from html.entities import html5
from html.parser import HTMLParser
from string import punctuation
from typing import Dict, List, Optional, Tuple, Union


@dataclass
class _Element:
    tag: str
    attrs: Dict[str, str]
    opening: str = ""
    closing: str = ""
    indent: str = ""
    children: List[Union[str, "_Element"]] = field(default_factory=list)

    def raw(self) -> str:
        return (
            self.opening
            + "".join(
                child if isinstance(child, str) else child.raw()
                for child in self.children
            )
            + self.closing
        )


_INLINE = {
    "b": ("**", "strong"),
    "strong": ("**", "strong"),
    "i": ("*", "emphasis"),
    "em": ("*", "emphasis"),
}
_BLOCKS = {"table", "p", "ul", "ol", "dl", "h1", "h2", "h3", "h4", "h5", "h6"}
_TAGS = (
    _BLOCKS
    | set(_INLINE)
    | {
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "td",
        "th",
        "caption",
        "li",
        "dt",
        "dd",
        "a",
        "code",
        "tt",
        "sub",
        "sup",
        "br",
    }
)


class _Parser(HTMLParser):
    def __init__(
        self,
        text: str,
        blocks: Dict[str, Tuple[str, str]],
        literals: Dict[str, str],
    ):
        super().__init__(convert_charrefs=False)
        self.blocks = blocks
        self.literals = literals
        self.block_pattern = (
            re.compile("(" + "|".join(re.escape(key) for key in blocks) + ")")
            if blocks
            else None
        )
        self.root = _Element("", {})
        self.stack = [self.root]
        self.source = text
        self.lines = text.split("\n")
        self.offsets = [0]
        for line in self.lines:
            self.offsets.append(self.offsets[-1] + len(line) + 1)
        self.consumed = 0
        self.feed(text)
        self.close()
        # HTMLParser can silently consume incomplete markup at EOF.
        if self.consumed < len(text):
            self.stack[-1].children.append(text[self.consumed :])

    def _offset(self):
        line, column = self.getpos()
        return self.offsets[line - 1] + column

    def _record(self, raw):
        offset = self._offset()
        if offset > self.consumed:
            self.stack[-1].children.append(self.source[self.consumed : offset])
        self.consumed = offset + len(raw)

    def _close_optional(self, tags, boundaries):
        for index in range(len(self.stack) - 1, 0, -1):
            tag = self.stack[index].tag
            if tag in tags:
                del self.stack[index:]
                break
            if tag in boundaries:
                break

    def handle_starttag(self, tag, attrs):
        raw = self.get_starttag_text()
        if tag not in _TAGS:
            # In particular, preserve C++ template arguments such as <T>.
            self.handle_data(raw)
            return
        self._record(raw)
        if tag in _BLOCKS:
            self._close_optional({"p"}, {"td", "th", "li"})
        if tag == "li":
            self._close_optional({"li"}, {"ul", "ol"})
        elif tag in {"dt", "dd"}:
            self._close_optional({"dt", "dd"}, {"dl"})
        elif tag in {"td", "th"}:
            self._close_optional({"td", "th"}, {"tr", "table"})
        elif tag == "tr":
            self._close_optional({"tr"}, {"table", "thead", "tbody", "tfoot"})
        line, column = self.getpos()
        prefix = self.lines[line - 1][:column]
        # Adjacent tags share the source line's enclosing indentation even
        # when another tag or prose precedes this one on that line.
        indent = prefix[: len(prefix) - len(prefix.lstrip())]
        if prefix.lstrip().startswith(".. note::"):
            indent += "   "
        element = _Element(tag, dict(attrs), raw, indent=indent)
        self.stack[-1].children.append(element)
        if tag != "br":
            self.stack.append(element)

    def handle_endtag(self, tag):
        offset = self._offset()
        raw = self.source[offset : self.source.find(">", offset) + 1]
        self._record(raw)
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                self.stack[index].closing = raw
                del self.stack[index:]
                return
        self.stack[-1].children.append(raw)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in _TAGS and tag != "br":
            self.stack.pop()

    def handle_data(self, data):
        self._record(data)
        parts = self.block_pattern.split(data) if self.block_pattern else [data]
        for part in parts:
            if part in self.blocks:
                text, indent = self.blocks[part]
                self.stack[-1].children.append(
                    _Element("literal", {}, opening=text, indent=indent)
                )
            elif part:
                if any(parent.tag == "a" for parent in self.stack):
                    # Restore protected inline literals as text, not HTML, so
                    # label flattening can escape all of their backticks.
                    for key, literal in self.literals.items():
                        part = part.replace(key, literal)
                self.stack[-1].children.append(part)

    def _reference(self, prefix, name):
        raw = prefix + name
        if self.source[self._offset() + len(raw) :].startswith(";"):
            raw += ";"
        self.handle_data(raw)

    def handle_entityref(self, name):
        self._reference("&", name)

    def handle_charref(self, name):
        self._reference("&#", name)

    def handle_comment(self, data):
        offset = self._offset()
        # HTMLParser also accepts whitespace in the closing delimiter (-- >).
        end = self.source.find(">", offset + 4 + len(data)) + 1
        raw = self.source[offset:end]
        self._record(raw)
        self.stack[-1].children.append(_Element("opaque", {}, raw))


def _unescape(text: str) -> str:
    # Doxygen prose contains C++ &references, not HTML's optional-semicolon
    # entities. Decode only complete, recognized references.
    def replace(match):
        name = match[1]
        if name.startswith("#"):
            return unescape(match[0])
        return html5.get(name + ";", match[0])

    return re.sub(
        r"&(#(?:[xX][0-9a-fA-F]+|[0-9]+)|[A-Za-z][A-Za-z0-9]*);", replace, text
    )


def _indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + line if line else "" for line in text.split("\n"))


def _label_text(element: Union[str, _Element]) -> str:
    """Flatten HTML formatting: reST hyperlink labels cannot nest markup."""
    if isinstance(element, str):
        return _unescape(element)
    if element.tag == "br":
        return " "
    if element.tag in {"code", "tt"}:
        return _unescape(
            "".join(
                child if isinstance(child, str) else child.raw()
                for child in element.children
            )
        )
    return "".join(_label_text(child) for child in element.children)


def _has_link_or_literal(element: _Element) -> bool:
    """Find links or literals rendered directly or through inline wrappers."""
    if not element.closing:
        return False
    if element.tag in {"code", "tt"}:
        return True
    if element.tag == "a" and element.attrs.get("href"):
        return True
    return element.tag in set(_INLINE) | {"a"} and any(
        isinstance(child, _Element) and _has_link_or_literal(child)
        for child in element.children
    )


def _join_inline(parts: List[Tuple[Union[str, _Element], str]]) -> str:
    """Separate generated inline markup from text without visible spaces."""
    parts = [(node, text) for node, text in parts if text]
    output: List[str] = []
    for index, (node, text) in enumerate(parts):
        if isinstance(node, _Element) and _has_link_or_literal(node):
            before = output[-1][-1] if output else ""
            after = parts[index + 1][1][0] if index + 1 < len(parts) else ""
            # These punctuation characters are valid reST delimiter boundaries.
            # Escaped spaces provide boundaries elsewhere but render invisibly.
            if before and not before.isspace() and before not in "\"'(<[{-/:":
                text = "\\ " + text
            if after and not after.isspace() and after not in "\"')>]}-/:.,;!?\\":
                text += "\\ "
        output.append(text)
    return "".join(output)


def _children(element: _Element, in_cell: bool = False) -> str:
    return _join_inline(
        [(child, _render(child, in_cell)) for child in element.children]
    )


def _table(element: _Element) -> str:
    rows = []
    caption = ""

    def collect(parent):
        nonlocal caption
        allowed = (
            {"tr", "thead", "tbody", "tfoot", "caption"}
            if parent.tag == "table"
            else {"tr"}
        )
        for child in parent.children:
            if isinstance(child, str):
                if child.strip():
                    return False
                continue
            if child.tag not in allowed:
                return False
            if child.tag == "tr":
                row = []
                for cell in child.children:
                    if isinstance(cell, str):
                        if cell.strip():
                            return False
                    elif cell.tag in {"td", "th"}:
                        row.append(cell)
                    else:
                        return False
                rows.append(row)
            elif child.tag in {"thead", "tbody", "tfoot"}:
                if not collect(child):
                    return False
            elif child.tag == "caption":
                caption = " ".join(_children(child).split())
        return True

    def unsupported(parent):
        return any(
            isinstance(child, _Element)
            and (
                child.tag == "table"
                or "colspan" in child.attrs
                or "rowspan" in child.attrs
                or unsupported(child)
            )
            for child in parent.children
        )

    if (
        not collect(element)
        or not element.closing
        or unsupported(element)
        or not rows
        or not rows[0]
        or any(len(row) != len(rows[0]) for row in rows)
    ):
        return element.raw()
    result = [".. list-table::" + (" " + caption if caption else "")]
    header_rows = 0
    for row in rows:
        if not all(cell.tag == "th" for cell in row):
            break
        header_rows += 1
    if header_rows == len(rows):
        return element.raw()
    if header_rows:
        result.append(f"   :header-rows: {header_rows}")
    result.append("")
    for row in rows:
        for index, cell in enumerate(row):
            content = _children(cell, in_cell=True).strip()
            if content and len(set(content)) == 1 and content[0] in punctuation:
                content = "\\" + content
            lines = content.split("\n")
            marker = "   * -" if index == 0 else "     -"
            result.append(marker + (" " + lines[0] if content else ""))
            result.extend("       " + line if line else "" for line in lines[1:])
    return "\n\n" + "\n".join(result) + "\n\n"


def _render(element: Union[str, _Element], in_cell: bool = False) -> str:
    if isinstance(element, str):
        text = _unescape(element)
        # Collapse source wrapping, not the RST structure generated by children.
        return re.sub(r"\s+", " ", text) if in_cell else text
    tag = element.tag
    if tag in {"opaque", "literal"} or (
        tag in set(_INLINE) | {"a", "code", "tt", "sub", "sup"} and not element.closing
    ):
        # An unpaired <code> or <sup> can be a C++ template argument.
        return element.raw()
    if tag == "table":
        return _table(element)
    text = _children(element, in_cell)
    if tag in _INLINE:
        # reST cannot nest references or literals inside emphasis. Preserve
        # their meaning and surrounding text without an incompatible wrapper.
        if _has_link_or_literal(element):
            return text
        marker, role = _INLINE[tag]
        return f":{role}:`{text}`" if "\n" in text else marker + text + marker
    if tag in {"sub", "sup"}:
        return f":{tag}:`{text}`"
    if tag in {"code", "tt"}:
        raw = "".join(c if isinstance(c, str) else c.raw() for c in element.children)
        return "``" + " ".join(_unescape(raw).split()) + "``"
    if tag == "a":
        href = element.attrs.get("href")
        label = " ".join(_label_text(element).split()).replace("`", r"\`")
        return f"`{label} <{href}>`__" if href else text
    if tag == "br":
        return "\n"
    if tag == "p":
        return "\n\n" + text.strip() + "\n\n"
    if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        return "\n\n.. rubric:: " + " ".join(text.split()) + "\n\n"
    if tag in {"ul", "ol"}:
        marker = "#. " if tag == "ol" else "- "
        items = []
        non_items: List[Tuple[Union[str, _Element], str]] = []

        def flush_non_items():
            # Loose documentation HTML can place prose or protected code
            # between items. Keep adjacent inline nodes together and retain
            # their source order, separating them from generated list segments.
            content = _join_inline(non_items).strip()
            if content:
                items.append("\n" + content + "\n")
            non_items.clear()

        for child in element.children:
            if isinstance(child, _Element) and child.tag == "li":
                flush_non_items()
                lines = _children(child, in_cell).strip().split("\n")
                items.append(
                    marker
                    + lines[0]
                    + "\n"
                    + _indent("\n".join(lines[1:]), " " * len(marker))
                )
            else:
                non_items.append((child, _render(child, in_cell)))
        flush_non_items()
        return "\n\n" + "\n".join(items).rstrip() + "\n\n"
    if tag == "li":
        return "\n- " + _indent(text.strip(), "  ").lstrip() + "\n"
    if tag == "dl":
        # Layout whitespace between dt/dd must not separate term and definition,
        # but actual prose or protected blocks must be retained in source order.
        entries = []
        non_entries: List[Tuple[Union[str, _Element], str]] = []

        def flush_non_entries():
            content = _join_inline(non_entries).strip()
            if content:
                entries.append("\n\n" + content + "\n\n")
            non_entries.clear()

        for child in element.children:
            if isinstance(child, _Element) and child.tag in {"dt", "dd"}:
                flush_non_entries()
                entries.append(_render(child, in_cell))
            else:
                non_entries.append((child, _render(child, in_cell)))
        flush_non_entries()
        return "\n\n" + "".join(entries).strip() + "\n\n"
    if tag == "dt":
        return "\n" + text.strip() + "\n"
    if tag == "dd":
        return _indent(text.strip(), "   ") + "\n"
    return text


def _remove_source_indent(element: _Element, indent: str) -> None:
    """Remove Doxygen's outer indentation before generating container layout."""
    for index, child in enumerate(element.children):
        if isinstance(child, str):
            element.children[index] = child.replace("\n" + indent, "\n")
        else:
            _remove_source_indent(child, indent)


def convert_html(text: str, blocks: Optional[Dict[str, Tuple[str, str]]] = None) -> str:
    """Convert HTML, inserting protected block nodes without parsing their text."""
    # The Doxygen pass has already converted {@code ...} into inline literals.
    # Protect those (and native reST literals) before handing prose to HTMLParser.
    prefix = "\x00sphinxify-literal-"
    while prefix in text:
        prefix += "-"
    literals: Dict[str, str] = {}

    def protect(match):
        key = prefix + str(len(literals)) + "\x00"
        literals[key] = match[0]
        return key

    text = re.sub(r"``.*?``", protect, text, flags=re.S)
    text = re.sub(r"(?m)^[ \t]+$", "", text)
    parser = _Parser(text, blocks or {}, literals)
    output: List[Tuple[Union[str, _Element], str]] = []
    continuation_indent = ""
    for child in parser.root.children:
        if isinstance(child, _Element) and child.tag in _BLOCKS and child.indent:
            _remove_source_indent(child, child.indent)
        rendered = _render(child)
        if isinstance(child, _Element) and child.tag == "br":
            # Nested breaks receive indentation from their containing block;
            # root-level breaks must carry the source's note indentation.
            rendered += child.indent
        is_block = isinstance(child, _Element) and child.tag in _BLOCKS | {"literal"}
        if not is_block and output and output[-1][1].endswith("\n\n"):
            rendered = rendered.lstrip(" \t")
            if rendered and not rendered.startswith("\n"):
                # Inline nodes need the same continuation layout as prose.
                # Their source indentation also tells us if the note has ended.
                indent = (
                    child.indent if isinstance(child, _Element) else continuation_indent
                )
                rendered = indent + rendered
        if is_block and isinstance(child, _Element):
            continuation_indent = child.indent
            if child.indent:
                rendered = _indent(rendered, child.indent)
        # Whitespace between a block and inline content must not hide the
        # paragraph boundary from the next node.
        if rendered:
            output.append((child, rendered))
    result = _join_inline(output)
    for key, literal in literals.items():
        result = result.replace(key, literal)
    return result
