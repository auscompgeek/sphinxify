#!/usr/bin/env python3
"""Convert Javadoc to Sphinx docstrings."""

import re
import sys
from typing import List, Tuple

__version__ = '0.1'

FIND_FUNC_RE = r'(.*)\n\s*((?:(?:public|protected|private|static|final|synchronized|abstract|default|native)\s+)+)(?:([\w<>[\]]+)\s+)?(\w+)\s*\(([^)]*)\)'

TYPE_MAPPING = {
    'ArrayList': 'List',

    '<': '[',
    '>': ']',

    'boolean': 'bool',
    'Boolean': 'bool',

    'Integer': 'int',
    'Long': 'int', 'long': 'int',
    'Short': 'int', 'short': 'int',
    'Byte': 'int', 'byte': 'int',

    'double': 'float',
    'Double': 'float',
    'Float': 'float',

    'String': 'str',
    'ByteBuffer': 'bytearray',  # java.nio
}


def trim_lines(lines: List[str]) -> List[str]:
    return '\n'.join(lines).strip().split('\n')


def process_doc(txt: str) -> str:
    params: List[Tuple[str, List[str]]] = []
    returns = []
    paramidx = -1
    found_returns = False

    lines = txt.splitlines()
    for i, line in enumerate(lines):
        line = line.strip()

        line = line.replace('/*', '').replace('*/', '')
        if line.startswith('*'):
            line = line[1:]

        line = line.replace('<p>', '')

        p = re.search(r'@param\W+(\w+)', line)
        if p:
            line = re.sub(r'@param\W+\w+(\W+)?', '', line)
            paramidx += 1
            params.append((p.group(1), []))
        else:
            r = re.search(r'@returns?\W*', line)
            if r:
                line = re.sub(r'@returns?\W*', '', line)
                found_returns = True

        line = re.sub(r'{@link\W+#(\w+?)\(.*?\)\W*}', r':meth:`.\1`', line)
        line = re.sub(r'{@link\W+(\w+)#(\w+)\(.*?\)\W*}', r':meth:`.\1.\2`', line)
        line = re.sub(r'{@link\W+#(\w+?)\W*}', r':class:`.\1`', line)

        line = line.strip()

        if found_returns:
            lines[i] = ''
            returns.append(line)

        elif paramidx != -1:
            lines[i] = ''
            params[paramidx][1].append(line)

        else:
            lines[i] = line

    text = '\n'.join(lines).strip()
    text = re.sub('\n{2,}', text, '\n\n')

    # indent each parameter evenly
    pindent = max((len(p[0]) for p in params), default=0)
    pindent_str = ' ' * pindent

    # indent each parameter and append
    for name, lines in params:
        pname = f':param {name}: '
        pp = trim_lines(lines)
        if not pp:
            continue

        text += f'\n{pname}{" " * (pindent - len(pname))}{pp[0]}\n'
        for line in pp[1:]:
            if line:
                text += f'{pindent_str}{line}\n'
            else:
                text += '\n'

    if returns:
        returns = trim_lines(returns)
        # returns always needs a newline before it
        text += '\n:returns: ' + returns[0]
        for line in returns[1:]:
            if line:
                text += ' '*10 + line + '\n'
            else:
                text += '\n'

    return text


def java_type_to_python(type: str) -> str:
    if type == 'void':
        return 'None'
    if type == 'byte[]':
        return 'bytes'

    is_array = False
    if type.endswith('[]'):
        is_array = True
        type = type[:-2]

    type_words = re.split(r'(\w+)', type)
    for i, word in enumerate(type_words):
        if word in TYPE_MAPPING:
            type_words[i] = TYPE_MAPPING[word]

    type = ''.join(type_words)
    if is_array:
        type = f'List[{type}]'

    return type


def format_docstring(text: str, indent: str = ' ' * 8) -> str:
    # indent all
    lines = text.splitlines()
    for i, line in enumerate(lines[1:], 1):
        if line:
            lines[i] = indent + line

    if len(lines) > 1:
        lines.append(indent)

    lines[-1] += '"""'
    return '"""' + '\n'.join(lines)


def process_raw(txt: str) -> str:
    # remove diff formatting if present
    txt = re.sub(r'(?m)^\+', '', txt)

    # try to find a function definition
    s = re.split(FIND_FUNC_RE, txt)
    return process_doc(s[0])


def process_yamlgen(txt: str) -> str:
    t = process_raw(txt)

    t = '  doc: |\n' + t.replace('\n', '\n' + ' '*4)
    return t


def process(txt: str) -> str:
    # remove diff formatting if present
    txt = re.sub(r'(?m)^\+', '', txt)

    # try to find a function definition
    s = re.split(FIND_FUNC_RE, txt)
    t = process_doc(s[0])

    t = format_docstring(t)

    # add the function definition in if present
    if len(s) > 1:
        modifiers, ret_type, func_name, args = s[2:6]
        
        if args:
            py_args = []
            for arg in args.split(', '):
                split = arg.split()
                if split[0] != 'final':
                    arg_type, arg_name = split
                else:
                    arg_type, arg_name = split[1:]
                py_args.append(f'{arg_name}: {java_type_to_python(arg_type)}')

            args = ', ' + ', '.join(py_args)

        if ret_type:
            ret_type = java_type_to_python(ret_type)
        else:
            func_name = '__init__'
            ret_type = 'None'

        if 'static' in modifiers:
            t = f'@classmethod\n    def {func_name}(cls{args}) -> {ret_type}:\n{" "*8}{t}'
        else:
            t = f'def {func_name}(self{args}) -> {ret_type}:\n{" "*8}{t}'

    return t


def main():
    text = sys.stdin.read()
    if len(sys.argv) > 1:
        if sys.argv[1] == 'yaml':
            print(process_yamlgen(text))
    else:
        print(process(text))


if __name__ == "__main__":
    main()
