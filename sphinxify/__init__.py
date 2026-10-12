"""Convert Javadoc/Doxygen to Sphinx reStructuredText docstrings."""

import collections
import re
import textwrap
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple, Union

from ._codeblocks import (
    CodeBlock,
    CodeBlockReplacement,
    CodeBlockTransform,
    split_comment,
)

__version__ = "0.13"

FIND_FUNC_RE = r"(.*)\n\s*((?:(?:public|protected|private|static|final|synchronized|abstract|default|native)\s+)+)(?:([\w<>[\]]+)\s+)?(\w+)\s*\(([^)]*)\)"

TYPE_MAPPING = {
    "ArrayList": "List",
    "<": "[",
    ">": "]",
    "boolean": "bool",
    "Boolean": "bool",
    "Integer": "int",
    "Long": "int",
    "long": "int",
    "Short": "int",
    "short": "int",
    "Byte": "int",
    "byte": "int",
    "double": "float",
    "Double": "float",
    "Float": "float",
    "String": "str",
    "ByteBuffer": "bytearray",  # java.nio
}


def trim_lines(lines: List[str]) -> List[str]:
    return "\n".join(lines).strip().split("\n")


@dataclass
class _Literal:
    block: CodeBlockReplacement
    indent: str


_Section = List[Union[str, _Literal]]


def _render_section(section: _Section) -> str:
    lines: List[str] = []
    for item in section:
        if isinstance(item, str):
            # Normalize prose blank lines, never the contents of a literal.
            if item.strip() or (lines and lines[-1] != ""):
                lines.append(item)
        else:
            if lines and lines[-1] != "":
                lines.append("")
            block = item.block
            directive = ".. code-block:: " + block.language if block.language else "::"
            lines.extend([item.indent + directive, ""])
            lines.extend(item.indent + "   " + line for line in block.text.split("\n"))
            lines.append("")
    return "\n".join(lines).strip()


@dataclass
class Param:
    #: The parameter name.
    name: str
    #: Lines describing the parameter.
    lines: List[str]


@dataclass
class Doc:
    #: The description prose before any parameters are listed.
    desc: str
    #: List of parameters.
    params: List[Param]
    #: The return value description (as a list of lines).
    returns: List[str]
    #: The deprecation message, if any.
    deprecated: Optional[List[str]] = None

    def __post_init__(self) -> None:
        #: Ordered mapping of parameter names and their descriptions.
        # We use OrderedDict here because we still support Python 3.6.
        self._params_dict = collections.OrderedDict((p.name, p) for p in self.params)

    @classmethod
    def from_comment(
        cls,
        txt: str,
        fix_method_name: Callable[[str], str] = lambda x: x,
        *,
        code_block_transform: Optional[CodeBlockTransform] = None,
    ) -> "Doc":
        """Create a Doc from a doc comment.

        Arguments:
            txt: The doc comment to convert.
            fix_method_name: A callback to convert method names in links.
            code_block_transform: Called once per source block, in source order.
                Return a CodeBlockReplacement, or None to preserve the block.

        Raises:
            ValueError: A recognized code block has no closing delimiter.
        """

        param_sections: List[Tuple[str, _Section]] = []
        returns: _Section = []
        deprecated: Optional[_Section] = None
        in_block = begin_block = False

        def make_self_method_ref(match) -> str:
            return f":meth:`.{fix_method_name(match[1])}`"

        def make_method_ref(match) -> str:
            cls_name = match[1]
            method = fix_method_name(match[2])
            return f":meth:`.{cls_name}.{method}`"

        lines: List[Union[str, CodeBlock]] = []
        after_block = False
        for chunk in split_comment(txt):
            if isinstance(chunk, CodeBlock):
                lines.append(chunk)
                after_block = True
            else:
                # The closing marker's newline is not an empty prose paragraph.
                if after_block and chunk.startswith("\n"):
                    chunk = chunk[1:]
                lines.extend(chunk.splitlines())
                after_block = False

        desc_lines: _Section = []
        current_lines = desc_lines
        for i, token in enumerate(lines):
            if isinstance(token, CodeBlock):
                replacement = (
                    code_block_transform(token) if code_block_transform else None
                )
                if replacement is None:
                    replacement = CodeBlockReplacement(token.text, token.language)
                current_lines.append(_Literal(replacement, "   " if in_block else ""))
                continue

            line = token.strip()
            if not line:
                # Layout whitespace before a block must not detach it from its
                # parameter, return, deprecation, or note section.
                following = next((t for t in lines[i + 1 :] if t), None)
                if not isinstance(following, CodeBlock):
                    if in_block:
                        in_block = False
                    elif current_lines is not returns:
                        current_lines = desc_lines

            if line.startswith((r"\fn ", r"\class ")):
                continue

            if line.startswith(("@brief ", r"\brief ")):
                line = line[len("@brief ") :]
            elif line.startswith(r"\enum "):
                line = " ".join(line.split()[2:])
            elif line.startswith("@deprecated "):
                deprecated = []
                in_block = False
                current_lines = deprecated
                line = line[len("@deprecated ") :]
            elif line.startswith("@note "):
                line = ".. note:: " + line[len("@note ") :]
                begin_block = True
            else:
                line = line.replace("<p>", "").replace("<br>", "\n")

                p = re.search(r"^[\\@]param\W+(\w+)", line)
                if p:
                    line = re.sub(r"^[\\@]param\W+\w+(\W+)?", "", line)
                    param_name = p.group(1)
                    current_lines = []
                    in_block = False
                    param_sections.append((param_name, current_lines))
                else:
                    r = re.search(r"^[\\@]returns?\W*", line)
                    if r:
                        line = re.sub(r"^[\\@]returns?\W*", "", line)
                        current_lines = returns
                        in_block = False

            line = re.sub(r"{@link #(\w+?)\(.*?\)\W*}", make_self_method_ref, line)
            line = re.sub(r"{@link (\w+)#(\w+)\(.*?\)\W*}", make_method_ref, line)
            line = re.sub(r"{@link #(\w+)\.(\w+)\W*}", make_method_ref, line)
            line = re.sub(
                r"{@link (?:[a-z]\w*\.)*([A-Z]\w+?)\W*}", r":class:`.\1`", line
            )

            line = re.sub(r"{@code ([^}]+)}", r"``\1``", line)

            line = line.replace("<ul>", "").replace("</ul>", "")
            line = line.replace("<li>", "- ").replace("</li>", "")
            if line.startswith(r"\li "):
                line = "-" + line[3:]

            for tag, inline, role in (
                ("b", "**", "strong"),
                ("strong", "**", "strong"),
                ("i", "*", "emphasis"),
                ("em", "*", "emphasis"),
            ):
                if line.count(f"<{tag}>") == line.count(f"</{tag}>"):
                    line = re.sub(rf"</?{tag}>", inline, line)
                else:
                    line = line.replace(f"<{tag}>", f":{role}:`")
                    line = line.replace(f"</{tag}>", "`")

            line = line.replace("<sub>", ":sub:`").replace("</sub>", "`")
            line = line.replace("<sup>", ":sup:`").replace("</sup>", "`")

            line = re.sub(r"\B_\b", r"\\_", line)

            line = line.strip()
            if in_block:
                line = " " * 3 + line
            elif begin_block:
                in_block = True
                begin_block = False

            current_lines.append(line)

        return cls(
            _render_section(desc_lines),
            params=[
                Param(name, _render_section(section).split("\n"))
                for name, section in param_sections
            ],
            returns=_render_section(returns).split("\n") if returns else [],
            deprecated=(
                _render_section(deprecated).split("\n")
                if deprecated is not None
                else None
            ),
        )

    def get_param(self, name: str) -> Optional[Param]:
        return self._params_dict.get(name)

    def remove_param(self, name: str) -> None:
        to_delete = self._params_dict[name]
        for i, param in enumerate(self.params):
            if param is to_delete:
                del self.params[i]
        del self._params_dict[name]

    def __str__(self) -> str:
        """Convert a Doc to Sphinx reST."""

        to_append = ["\n"]

        if self.deprecated is not None:
            to_append.append(":deprecated: " + self.deprecated[0])
            to_append += [" " * 13 + line for line in self.deprecated[1:]]

            # keep params in their own list
            to_append.append("")

        if self.params:
            # indent each parameter evenly
            pindent = max(len(p.name) for p in self.params) + len(":param : ")
            pindent_str = " " * pindent

            # indent each parameter and append
            for param in self.params:
                pname = f":param {param.name}: "
                pp = trim_lines(param.lines)

                to_append.append(f'{pname}{" " * (pindent - len(pname))}{pp[0]}')
                to_append += [pindent_str + line for line in pp[1:]]

            # make sure there is a blank line between params and returns
            to_append.append("")

        if self.returns:
            returns = trim_lines(self.returns)
            to_append.append(":returns: " + returns[0])
            to_append += [" " * 10 + line for line in returns[1:]]

        return self.desc + "\n".join(to_append).rstrip()


def process_doc(
    txt: str, *, code_block_transform: Optional[CodeBlockTransform] = None
) -> str:
    """Convert a doc comment to Sphinx reST, optionally transforming code blocks."""

    return str(Doc.from_comment(txt, code_block_transform=code_block_transform))


def java_type_to_python(type: str) -> str:
    """Turn a Java type into a Python type hint."""

    if type == "void":
        return "None"
    if type == "byte[]":
        return "bytes"

    is_array = False
    if type.endswith("[]"):
        is_array = True
        type = type[:-2]

    type_words = re.split(r"(\w+)", type)
    for i, word in enumerate(type_words):
        if word in TYPE_MAPPING:
            type_words[i] = TYPE_MAPPING[word]

    type = "".join(type_words)
    if is_array:
        type = f"List[{type}]"

    return type


def format_docstring(text: str, indent: str = " " * 8) -> str:
    """Wrap a doc string to be valid Python source for a docstring."""

    raw_prefix = "r" if "\\" in text else ""

    if text.count("\n") == 0:
        return f'{indent}{raw_prefix}"""{text}"""'

    return textwrap.indent(f'{raw_prefix}"""{text}\n"""', indent)


def process_raw(
    txt: str, *, code_block_transform: Optional[CodeBlockTransform] = None
) -> str:
    """Convert the first doc comment in txt into Sphinx reST."""

    # remove diff formatting if present
    txt = re.sub(r"(?m)^\+", "", txt)

    # try to find a function definition
    s = re.split(FIND_FUNC_RE, txt)
    return process_doc(s[0], code_block_transform=code_block_transform)


def process_yamlgen(txt: str) -> str:
    t = process_raw(txt)

    t = "  doc: |\n" + textwrap.indent(t, " " * 4)
    return t


def process_cstring(txt: str) -> str:
    t = process_raw(txt)
    return '"{}"'.format(t.replace("\\", "\\\\").replace("\n", '\\n"\n"'))


def process_comment(txt: str) -> str:
    t = process_raw(txt)
    return " " * 4 + "#: " + t.replace("\n", "\n" + " " * 4 + "#: ")


def process(txt: str) -> str:
    """Convert the first Java method in txt into a Python stub."""

    # remove diff formatting if present
    txt = re.sub(r"(?m)^\+", "", txt)

    # try to find a function definition
    s = re.split(FIND_FUNC_RE, txt)
    t = process_doc(s[0])

    t = format_docstring(t)

    # add the function definition in if present
    if len(s) > 1:
        modifiers, ret_type, func_name, args = s[2:6]

        if args:
            py_args = []
            for arg in args.split(", "):
                split = arg.split()
                if split[0] != "final":
                    arg_type, arg_name = split
                else:
                    arg_type, arg_name = split[1:]
                py_args.append(f"{arg_name}: {java_type_to_python(arg_type)}")

            args = ", " + ", ".join(py_args)

        if ret_type:
            ret_type = java_type_to_python(ret_type)
        else:
            func_name = "__init__"
            ret_type = "None"

        if "static" in modifiers:
            t = f"    @classmethod\n    def {func_name}(cls{args}) -> {ret_type}:\n{t}"
        else:
            t = f"    def {func_name}(self{args}) -> {ret_type}:\n{t}"

    return t
