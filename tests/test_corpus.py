import subprocess
import sys
from pathlib import Path

import pytest
from docutils import nodes
from docutils.core import publish_doctree
from docutils.parsers.rst import roles

TESTS_DIR = Path(__file__).resolve().parent


def read_corpus(path):
    lines = path.read_bytes().splitlines(keepends=True)
    separators = [i for i, line in enumerate(lines) if line == b"=" * 80 + b"\n"]
    if len(separators) != 1:
        raise ValueError(
            f"{path}: expected exactly one separator line of 80 '=' characters"
        )
    index = separators[0]
    return b"".join(lines[:index]), b"".join(lines[index + 1 :])


def test_read_corpus_preserves_whitespace(tmp_path):
    path = tmp_path / "case.txt"
    path.write_bytes(b"/** raw */  \n\n" + b"=" * 80 + b"\n\n  output  \n\n")

    assert read_corpus(path) == (b"/** raw */  \n\n", b"\n  output  \n\n")


@pytest.mark.parametrize(
    "contents",
    [
        b"no separator\n",
        b"=" * 79 + b"\n",
        b"=" * 81 + b"\n",
        b"prefix" + b"=" * 80 + b"\n",
        (b"=" * 80 + b"\n") * 2,
    ],
)
def test_read_corpus_rejects_invalid_separator(tmp_path, contents):
    path = tmp_path / "case.txt"
    path.write_bytes(contents)

    with pytest.raises(ValueError, match="exactly one separator"):
        read_corpus(path)


@pytest.mark.parametrize(
    "corpus_path",
    sorted((TESTS_DIR / "corpus").glob("*.txt")),
    ids=lambda path: path.name,
)
def test_raw_corpus(corpus_path, monkeypatch):
    raw, expected = read_corpus(corpus_path)
    result = subprocess.run(
        [sys.executable, "-m", "sphinxify", "raw"],
        input=raw,
        capture_output=True,
        check=True,
    )

    assert result.stdout == expected

    # Accept the corpus's Sphinx role without resolving its cross-reference.
    # Isolate docutils' process-global registry so other tests are unaffected.
    monkeypatch.setattr(roles, "_roles", roles._roles.copy())
    roles.register_local_role(
        "class", roles.GenericRole("class", nodes.title_reference)
    )

    # Exact output catches conversion changes; parsing also catches invalid
    # nesting or indentation that can look plausible in a text fixture.
    tree = publish_doctree(
        result.stdout.decode("utf-8"), settings_overrides={"halt_level": 2}
    )
    assert not list(tree.findall(nodes.system_message))
