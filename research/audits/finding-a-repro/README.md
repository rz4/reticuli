# Finding A reproduction — excluded guidance can decide acceptance

`sh run.sh` (needs `ret` on PATH). Seals a format-3 claim whose gate reads its
own producer guidance, then edits only the guidance and re-audits. Expected:
the manifest root is identical and `verify` keeps passing (guidance is stripped
from the root at format 3), yet `audit` flips from PASS to FAIL — because
`_materialize` copies the guidance-bearing recipe into the judging room. Same
root, different acceptance. See ../2026-09-22-cross-family-essence-and-soundness.md.
