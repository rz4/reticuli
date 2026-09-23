"""Config parser D2: first key wins, all values left as strings."""


def parse(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key not in out:            # first assignment wins
            out[key] = value.strip()
    return out
