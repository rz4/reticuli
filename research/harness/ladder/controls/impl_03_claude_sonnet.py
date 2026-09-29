def parse(text: str) -> dict:
    result = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result
