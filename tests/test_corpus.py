import subprocess
import sys
from pathlib import Path

import pytest
from docutils import nodes
from docutils.core import publish_doctree
from docutils.parsers.rst import roles

TESTS_DIR = Path(__file__).resolve().parent


@pytest.mark.parametrize(
    "input_path",
    sorted((TESTS_DIR / "input").glob("*.txt")),
    ids=lambda path: path.name,
)
def test_raw_corpus(input_path, monkeypatch):
    result = subprocess.run(
        [sys.executable, "-m", "sphinxify", "raw"],
        input=input_path.read_bytes(),
        capture_output=True,
        check=True,
    )

    assert result.stdout == (TESTS_DIR / "expected" / input_path.name).read_bytes()

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
