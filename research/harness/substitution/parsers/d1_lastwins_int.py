"""Config parser D1: last key wins, numeric values coerced to int."""


def parse(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if value.lstrip("-").isdigit():
            value = int(value)
        out[key] = value  # last assignment wins
    return out
