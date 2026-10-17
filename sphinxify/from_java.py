"""Finds a Java method declaration (if any) and converts the Javadoc."""

import re
import textwrap

from sphinxify import process_doc

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


def format_docstring(text: str, indent: str = " " * 8) -> str:
    """Wrap a doc string to be valid Python source for a docstring."""

    raw_prefix = "r" if "\\" in text else ""

    if text.count("\n") == 0:
        return f'{indent}{raw_prefix}"""{text}"""'

    return textwrap.indent(f'{raw_prefix}"""{text}\n"""', indent)


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
