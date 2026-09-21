#!/usr/bin/env python3
import sys

from sphinxify import process_comment, process_cstring, process_raw
from sphinxify import process, process_yamlgen


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        from sphinxify.server import SphinxifyServer

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
