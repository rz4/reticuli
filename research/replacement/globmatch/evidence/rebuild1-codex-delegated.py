"""Shell-style filename pattern matching using standard-library semantics."""

import fnmatch


def match(pattern, name):
    """Return whether the whole name matches the fnmatch-style pattern."""
    return fnmatch.fnmatch(name, pattern)
