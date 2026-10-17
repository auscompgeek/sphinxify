"""Convert Javadoc/Doxygen to Sphinx reStructuredText docstrings."""

import collections
import re
import warnings
from dataclasses import dataclass
from typing import Callable, List, Optional

__version__ = "0.13"


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
        self._params_dict = {p.name: p for p in self.params}

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


def process_raw(txt: str) -> str:
    """
    Convert the first doc comment in txt into Sphinx reST.

    .. deprecated:: 0.13
       Use :func:`sphinxify.from_java.process_raw` instead.
    """
    from sphinxify.from_java import process_raw

    warnings.warn(
        "Use sphinxify.from_java.process_raw instead", DeprecationWarning, stacklevel=2
    )
    return process_raw(txt)
