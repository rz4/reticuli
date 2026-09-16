#!/bin/sh
# The acceptance test: pinned, so its bytes are part of the claim's identity.
#
# Note what this does NOT do: pipe into `diff -`. A gate runs sandboxed, with
# writes permitted only inside the claim, and BSD diff spools non-seekable
# stdin to a temp file in the system temp directory — which is denied. A gate
# that leans on a tool needing scratch space outside the claim passes on every
# host without a working sandbox and fails on every host with one. Comparing
# in the shell needs no scratch space at all.
set -e
got=$(./wordcount < cases/input.txt)
want=$(cat cases/expected.txt)
if [ "$got" != "$want" ]; then
    echo "wordcount: want [$want], got [$got]" >&2
    exit 1
fi
printf ok > OK
