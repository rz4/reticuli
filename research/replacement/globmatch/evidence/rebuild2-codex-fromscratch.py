"""Case-sensitive shell wildcard matching without path-specific rules."""


def _class(pattern, start):
    """Return a parsed bracket class and its end, or None if unclosed."""
    end = start + 1
    negate = end < len(pattern) and pattern[end] == '!'
    if negate:
        end += 1
    first = end
    if end < len(pattern) and pattern[end] == ']':
        end += 1
    while end < len(pattern) and pattern[end] != ']':
        end += 1
    if end == len(pattern):
        return None
    body = pattern[first:end]
    parts = []
    i = 0
    while i < len(body):
        if i + 2 < len(body) and body[i + 1] == '-':
            parts.append((body[i], body[i + 2]))
            i += 3
        else:
            parts.append((body[i], body[i]))
            i += 1
    return (negate, parts), end + 1


def match(pattern, name):
    """Match an entire name using *, ?, and bracket classes.

    Slashes and leading dots are ordinary characters. Backslashes are
    literal, and an unclosed bracket is treated as a literal opening bracket.
    """
    tokens = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == '[':
            parsed = _class(pattern, i)
            if parsed is not None:
                value, i = parsed
                tokens.append(('class', value))
                continue
        if char == '*':
            if not tokens or tokens[-1][0] != '*':
                tokens.append(('*', None))
        elif char == '?':
            tokens.append(('?', None))
        else:
            tokens.append(('literal', char))
        i += 1

    # Each row records which name prefixes the pattern prefix can match.
    previous = [True] + [False] * len(name)
    for kind, value in tokens:
        current = [False] * (len(name) + 1)
        if kind == '*':
            current[0] = previous[0]
            for j in range(1, len(name) + 1):
                current[j] = previous[j] or current[j - 1]
        else:
            for j, char in enumerate(name, 1):
                if kind == '?':
                    accepts = True
                elif kind == 'literal':
                    accepts = char == value
                else:
                    negate, parts = value
                    accepts = any(low <= char <= high for low, high in parts)
                    if negate:
                        accepts = not accepts
                current[j] = previous[j - 1] and accepts
        previous = current
    return previous[-1]
