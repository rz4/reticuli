#!/bin/sh
# The acceptance test: pinned, so its bytes are part of the claim's identity.
set -e
./wordcount < cases/input.txt | diff -u cases/expected.txt -
printf ok > OK
