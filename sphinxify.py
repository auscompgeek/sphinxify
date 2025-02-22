#!/usr/bin/env python3
"""Convert Javadoc to Sphinx docstrings."""

import collections
import json
import re
import sys
import textwrap
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable, List, Optional

__version__ = "0.12"

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
        in_pre = in_block = begin_block = False

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
            elif line.startswith("/// "):
                line = line[4:]
            else:
                line = line.replace("/*", "").replace("*/", "")
                if line == "*":
                    line = ""
                elif line.startswith("* "):
                    line = line[2:]
                elif line.startswith("*< "):
                    line = line[3:]

            if line in ("<pre>", "@code"):
                in_pre = True
                current_lines.append("::\n")
                continue
            elif line in ("</pre>", "@endcode"):
                in_pre = False
                line = ""
            elif in_block and line == "":
                in_block = False
            elif in_pre:
                current_lines.append("  " + line)
                continue
            elif line.startswith("@code "):
                in_pre = True
                current_lines.append("::\n")
                current_lines.append("  " + line[6:])
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
                    params.append(Param(param_name, current_lines))
                else:
                    r = re.search(r"^[\\@]returns?\W*", line)
                    if r:
                        line = re.sub(r"^[\\@]returns?\W*", "", line)
                        current_lines = returns

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

        text = "\n".join(desc_lines).strip()
        text = re.sub("\n{2,}", "\n\n", text)

        return cls(text, params=params, returns=returns, deprecated=deprecated)

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

    raw_prefix = "r" if "\\" in text else ""

    if text.count("\n") == 0:
        return f'{indent}{raw_prefix}"""{text}"""'

    return textwrap.indent(f'{raw_prefix}"""{text}\n"""', indent)


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


class SphinxifyServer(BaseHTTPRequestHandler):

    protocol_version = "HTTP/1.0"

    index_html = b"""
        <!DOCTYPE html>
        <html>
            <head></head>
            <body>
            In: doxygen contents<br/>
            <textarea id="inbox" rows="20" cols="100"></textarea><br/>
            Out: python docstring<br/>
            <textarea id="outbox" rows="20" cols="100"></textarea><br/>
            Out: raw<br/>
            <textarea id="rawbox" rows="20" cols="100"></textarea>

            <script>

            function xfer() {
                let data = {inbox: inbox.value}
                fetch("/sphinxify", {
                    method: "POST",
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data),
                }).then(res => {
                    res.json().then(res => {
                        outbox.value = res.outbox;
                        rawbox.value = res.rawbox;
                    })
                });
            }

            inbox.oninput = inbox.onpropertychange = inbox.onpaste = xfer;
            xfer();

            </script>
        </html>
        """

    @classmethod
    def run(cls, port=5678):
        server = HTTPServer(("127.0.0.1", port), cls)
        url = f"http://127.0.0.1:{port}/"
        print("Sphinxify server listening at", url)

        webbrowser.open(url)
        server.serve_forever()

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(self.index_html)))
            self.end_headers()
            self.wfile.write(self.index_html)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/sphinxify":
            length = int(self.headers["content-length"])
            postdata = json.loads(self.rfile.read(length).decode("utf-8"))
            docstring = process(postdata["inbox"])
            raw = process_raw(postdata["inbox"])
            response = json.dumps({"outbox": docstring, "rawbox": raw})

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response.encode("utf-8"))
        else:
            self.send_error(404)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        SphinxifyServer.run()
        return

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
