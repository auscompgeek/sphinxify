#!/bin/sh
cd "$(dirname "$0")"
code=0

for f in input/*.txt; do
	python -m sphinxify raw < $f | diff -u - expected/$(basename $f) || code=$?
done

exit $code
