"""Parse newline-separated key/value assignments."""


def parse(text):
    result = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        try:
            value = int(value)
        except ValueError:
            pass
        result[key] = value
    return result
