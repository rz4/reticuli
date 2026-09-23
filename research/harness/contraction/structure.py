"""Structural diversity: how different the survivors are *under the hood*.

This is the metric that keeps the whole thesis honest. Behavioral agreement is
only interesting if it survives while structure stays diverse; if structure
collapses too, the boundary is just herding everyone onto one implementation.

d_struct is deliberately blind to naming and layout: source is canonicalized
(comments and whitespace dropped, identifiers normalized to a single
placeholder) and compared as a token sequence, so the distance measures shape,
not surface. Frozen at generation 0.
"""

from __future__ import annotations

import io
import keyword
import tokenize


def canonical_tokens(src: str) -> list[str]:
    """Token shape with names normalized. Falls back to characters if the
    source will not tokenize (a producer may emit something odd)."""
    skip = {
        tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
        tokenize.DEDENT, tokenize.ENCODING, tokenize.ENDMARKER,
    }
    out: list[str] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in skip:
                continue
            if tok.type == tokenize.NAME:
                out.append(tok.string if keyword.iskeyword(tok.string) else "v")
            elif tok.type == tokenize.NUMBER:
                out.append("n")
            elif tok.type == tokenize.STRING:
                out.append("s")
            else:
                out.append(tok.string)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return list(src)
    return out


def _levenshtein(a: list[str], b: list[str]) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def distance(src_a: str, src_b: str) -> float:
    """Normalized token edit distance in [0, 1]."""
    a, b = canonical_tokens(src_a), canonical_tokens(src_b)
    denom = max(len(a), len(b)) or 1
    return _levenshtein(a, b) / denom


def dist_matrix(sources: dict[str, str]) -> dict[str, dict[str, float]]:
    names = list(sources)
    out: dict[str, dict[str, float]] = {a: {} for a in names}
    for i, a in enumerate(names):
        for b in names[i:]:
            d = 0.0 if a == b else distance(sources[a], sources[b])
            out[a][b] = out[b][a] = d
    return out


def mean_pairwise(mtx: dict[str, dict[str, float]]) -> float:
    names = list(mtx)
    pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]]
    return sum(mtx[a][b] for a, b in pairs) / len(pairs) if pairs else 0.0


def clusters(mtx: dict[str, dict[str, float]], tau: float) -> list[list[str]]:
    """Union-find: implementations within tau of each other are one cluster.
    The count is the structural-diversity floor the pre-registration guards."""
    names = list(mtx)
    parent = {a: a for a in names}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if mtx[a][b] <= tau:
                parent[find(a)] = find(b)

    groups: dict[str, list[str]] = {}
    for a in names:
        groups.setdefault(find(a), []).append(a)
    return list(groups.values())
