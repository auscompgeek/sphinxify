# sphinxify
Convert Javadoc and Doxygen to Sphinx reStructuredText docstrings.

## Why?
The [RobotPy][] project ports Java libraries to Python.

A converter was originally written in HTML + JavaScript, but then the need to
be able to programmatically convert doc comments arose.

This also makes it easier to use in certain editors such as vim...

## Usage
Run `sphinxify` and give it a Javadoc comment.  It will keep reading until EOF.

If a Java function prototype is also given, sphinxify will also output a
Python type-hinted function signature.

You can also run `sphinxify server` and it will pop up a browser that you can
use to run sphinxify on the input also.

There is also a `sphinxify yaml` mode for the [robotpy-ctre][].

## Transforming code examples

`Doc.from_comment`, `process_doc`, and `process_raw` accept an optional
keyword-only `code_block_transform` callback:

```python
from sphinxify import CodeBlockReplacement, process_doc


def python_example(block):
    if block.index == 0:
        return CodeBlockReplacement("timer.start()", language="python")
    return None  # Preserve other blocks, including diagrams.


rst = process_doc(comment, code_block_transform=python_example)
```

The callback receives a `CodeBlock` with `text`, optional `language`, `kind`
(`doxygen`, `pre`, or `fence`), and a zero-based `index`. Indices follow source
order across the whole comment, including parameter, return, and deprecation
sections. Return a `CodeBlockReplacement(text, language=None)` to replace a
block, or `None` to retain its content and language. The API is language-neutral;
it does not translate source code automatically.

Supported block forms include `@code`/`\\code` (with optional `{.cpp}` language
annotations), `<pre>`, `<pre><code>`, and Markdown backtick/tilde fences.
Doxygen and HTML delimiters may share a line with code or surrounding prose.
Inline `{@code ...}` expressions are not blocks. Unterminated recognized blocks
raise `ValueError` with their kind and index.

Blocks retain relative indentation and internal blank lines. Labeled blocks
render as `.. code-block:: language`; unlabeled blocks use reST literal blocks.
They remain in their original documentation section.

To run the tests, install `tests/requirements.txt`, then run `python -m pytest`
from the repository root.

[RobotPy]: https://robotpy.github.io
[robotpy-ctre]: https://github.com/robotpy/robotpy-ctre
