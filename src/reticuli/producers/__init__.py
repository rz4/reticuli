"""Producers: programs that regenerate a claim's generated outputs.

A producer is any program `rebuild` can invoke. It need not involve a model:
for an ordinary reproducible build the producer is a compiler or a Makefile.
The ones shipped here drive a language model against a claim's acceptance
tests, for claims whose implementation is meant to be re-derived rather than
compiled.

    ret rebuild <claim> --producer "python3 -m reticuli.producers.openai" --into M3

The protocol is environment-variable based: RETICULI_OUTPUT names the file to
write, RETICULI_USAGE names a JSON file to report cost into.
"""
