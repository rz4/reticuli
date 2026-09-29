import re

_INT = re.compile(r"-?\d+")


def parse(text):
    result = {}
    section = ""
    text = text.replace("\\\n", "")
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue
        positions = [p for p in (line.find("="), line.find(":")) if p >= 0]
        if not positions:
            continue
        cut = min(positions)
        key = line[:cut].strip().lower()
        if section:
            key = section + "." + key
        value = line[cut + 1:].strip()
        if _INT.fullmatch(value):
            value = int(value)
        if key not in result:
            result[key] = value
    return result
