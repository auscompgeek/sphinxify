#!/usr/bin/env python3
"""Convert Javadoc to Sphinx docstrings."""

import re
import sys
import textwrap
from dataclasses import dataclass
from typing import Callable, List, Tuple

__version__ = "0.6.1"

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
class Doc:
    #: The description prose before any parameters are listed.
    desc: str
    #: List of all the parameter names and their descriptions (as a list of lines).
    params: List[Tuple[str, List[str]]]
    #: The return value description (as a list of lines).
    returns: List[str]

    @classmethod
    def from_comment(
        cls, txt: str, fix_method_name: Callable[[str], str] = lambda x: x
    ) -> "Doc":
        """Create a Doc from a doc comment.

        Arguments:
            txt: The doc comment to convert.
            fix_method_name: A callback to convert method names in links.
        """

        params: List[Tuple[str, List[str]]] = []
        returns = []
        paramidx = -1
        found_returns = False

        def make_self_method_ref(match) -> str:
            return f":meth:`.{fix_method_name(match[1])}`"

        def make_method_ref(match) -> str:
            cls_name = match[1]
            method = fix_method_name(match[2])
            return f":meth:`.{cls_name}.{method}`"

        lines = txt.splitlines()
        new_lines = []
        for line in lines:
            line = line.strip()

            line = line.replace("/*", "").replace("*/", "")
            if line.startswith("*"):
                line = line[1:].lstrip()

            if line.startswith((r"\fn ", r"\class ")):
                continue

            if line.startswith(r"\brief "):
                line = line[len(r"\brief ") :]
            elif line.startswith(r"\enum "):
                line = " ".join(line.split()[2:])
            else:
                line = line.replace("<p>", "").replace("<br>", "\n")

            p = re.search(r"^[\\@]param\W+(\w+)", line)
            if p:
                line = re.sub(r"^[\\@]param\W+\w+(\W+)?", "", line)
                paramidx += 1
                params.append((p.group(1), []))
            else:
                r = re.search(r"^[\\@]returns?\W*", line)
                if r:
                    line = re.sub(r"^[\\@]returns?\W*", "", line)
                    found_returns = True

            line = re.sub(r"{@link #(\w+?)\(.*?\)\W*}", make_self_method_ref, line)
            line = re.sub(r"{@link (\w+)#(\w+)\(.*?\)\W*}", make_method_ref, line)
            line = re.sub(r"{@link #(\w+)\.(\w+)\W*}", make_method_ref, line)
            line = re.sub(r"{@link #(\w+?)\W*}", r":class:`.\1`", line)

            line = re.sub(r"{@code ([^}]+)}", r"``\1``", line)

            line = line.replace("<ul>", "").replace("</ul>", "")
            line = line.replace("<li>", "- ").replace("</li>", "")
            if line.startswith(r"\li "):
                line = "-" + line[3:]

            line = re.sub(r"</?b>", "**", line)
            line = re.sub(r"</?i>", "*", line)
            line = line.strip()

            if found_returns:
                returns.append(line)

            elif paramidx != -1:
                params[paramidx][1].append(line)

            else:
                new_lines.append(line)

        text = "\n".join(new_lines).strip()
        text = re.sub("\n{2,}", "\n\n", text)

        return cls(text, params=params, returns=returns)

    def __str__(self) -> str:
        """Convert a Doc to Sphinx reST."""

        to_append = [""]

        # indent each parameter evenly
        pindent = max((len(p[0]) for p in self.params), default=0)
        pindent_str = " " * pindent

        # indent each parameter and append
        for name, lines in self.params:
            pname = f":param {name}: "
            pp = trim_lines(lines)
            if not pp:
                continue

            to_append.append(f'\n{pname}{" " * (pindent - len(pname))}{pp[0]}')
            for line in pp[1:]:
                if line:
                    to_append.append(f"{pindent_str}{line}")
                else:
                    to_append.append("")

        if self.returns:
            returns = trim_lines(self.returns)
            # returns always needs a newline before it
            to_append.append("\n:returns: " + returns[0])
            for line in returns[1:]:
                if line:
                    to_append.append(" " * 10 + line)
                else:
                    to_append.append("")

        return self.desc + "\n".join(to_append)


def process_doc(txt: str) -> str:
    """Convert a doc comment to Sphinx reST."""

    return str(Doc.from_comment(txt))


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

    if text.count("\n") == 0:
        return f'{indent}"""{text}"""'

    return textwrap.indent('"""{}\n"""'.format(text), indent)


def process_raw(txt: str) -> str:
    """Convert the first doc comment in txt into Sphinx reST."""

    # remove diff formatting if present
    txt = re.sub(r"(?m)^\+", "", txt)

    # try to find a function definition
    s = re.split(FIND_FUNC_RE, txt)
    return process_doc(s[0])


def process_yamlgen(txt: str) -> str:
    t = process_raw(txt)

    t = "  doc: |\n" + textwrap.indent(t, " " * 4)
    return t


def process_cstring(txt: str) -> str:
    t = process_raw(txt)
    return '"{}"'.format(t.replace("\n", '\\n"\n"'))


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


def main():
    text = sys.stdin.read()
    if len(sys.argv) > 1:
        modes = {
            "yaml": process_yamlgen,
            "raw": process_raw,
            "cstring": process_cstring,
            "comment": process_comment,
        }
        print(modes[sys.argv[1]](text))
    else:
        print(process(text))


if __name__ == "__main__":
    main()
