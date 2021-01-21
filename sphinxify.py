#!/usr/bin/env python3
"""Convert Javadoc to Sphinx docstrings."""

import collections
import re
import sys
import textwrap
from dataclasses import dataclass
from typing import Callable, List, Optional

__version__ = "0.8"

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
        cls, txt: str, fix_method_name: Callable[[str], str] = lambda x: x
    ) -> "Doc":
        """Create a Doc from a doc comment.

        Arguments:
            txt: The doc comment to convert.
            fix_method_name: A callback to convert method names in links.
        """

        params: List[Param] = []
        returns: List[str] = []
        deprecated: Optional[List[str]] = None
        in_pre = False

        def make_self_method_ref(match) -> str:
            return f":meth:`.{fix_method_name(match[1])}`"

        def make_method_ref(match) -> str:
            cls_name = match[1]
            method = fix_method_name(match[2])
            return f":meth:`.{cls_name}.{method}`"

        lines = txt.splitlines()
        desc_lines: List[str] = []
        current_lines = desc_lines
        for line in lines:
            line = line.strip()

            if line.startswith("//!< "):
                line = line[5:]
            else:
                line = line.replace("/*", "").replace("*/", "")
                if line == "*":
                    line = ""
                elif line.startswith("* "):
                    line = line[2:]
                elif line.startswith("*< "):
                    line = line[3:]

            if line == "<pre>":
                in_pre = True
                current_lines.append("::\n")
                continue
            elif line == "</pre>":
                in_pre = False
                line = ""
            elif in_pre:
                current_lines.append("  " + line)
                continue
            elif not line and current_lines is not returns:
                current_lines = desc_lines

            line = line.lstrip()

            if line.startswith((r"\fn ", r"\class ")):
                continue

            if line.startswith(("@brief ", r"\brief ")):
                line = line[len("@brief ") :]
            elif line.startswith(r"\enum "):
                line = " ".join(line.split()[2:])
            elif line.startswith("@deprecated "):
                deprecated = []
                current_lines = deprecated
                line = line[len("@deprecated ") :]
            else:
                line = line.replace("<p>", "").replace("<br>", "\n")

                p = re.search(r"^[\\@]param\W+(\w+)", line)
                if p:
                    line = re.sub(r"^[\\@]param\W+\w+(\W+)?", "", line)
                    param_name = p.group(1)
                    current_lines = []
                    params.append(Param(param_name, current_lines))
                else:
                    r = re.search(r"^[\\@]returns?\W*", line)
                    if r:
                        line = re.sub(r"^[\\@]returns?\W*", "", line)
                        current_lines = returns

            line = re.sub(r"{@link #(\w+?)\(.*?\)\W*}", make_self_method_ref, line)
            line = re.sub(r"{@link (\w+)#(\w+)\(.*?\)\W*}", make_method_ref, line)
            line = re.sub(r"{@link #(\w+)\.(\w+)\W*}", make_method_ref, line)
            line = re.sub(r"{@link #(\w+?)\W*}", r":class:`.\1`", line)

            line = re.sub(r"{@code ([^}]+)}", r"``\1``", line)

            line = line.replace("<ul>", "").replace("</ul>", "")
            line = line.replace("<li>", "- ").replace("</li>", "")
            if line.startswith(r"\li "):
                line = "-" + line[3:]

            line = re.sub(r"</?(b|strong)>", "**", line)
            line = re.sub(r"</?i>", "*", line)
            line = line.strip()

            current_lines.append(line)

        text = "\n".join(desc_lines).strip()
        text = re.sub("\n{2,}", "\n\n", text)

        return cls(text, params=params, returns=returns, deprecated=deprecated)

    def get_param(self, name: str) -> Param:
        return self._params_dict[name]

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
