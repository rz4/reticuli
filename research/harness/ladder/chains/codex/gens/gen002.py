"""Read a small, sectioned key-value format."""

import re


INTEGER = re.compile(r"-?\d+\Z")


def parse(text):
    result = {}
    section = ""

    for line in text.replace("\\\n", "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue

        parts = re.split(r"[=:]", line, maxsplit=1)
        if len(parts) == 1:
            continue

        name, value = (part.strip() for part in parts)
        name = name.lower()
        key = f"{section}.{name}" if section else name
        if key not in result:
            result[key] = int(value) if INTEGER.fullmatch(value) else value

    return result
