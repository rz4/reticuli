"""Parse a small key = value configuration text into a dict."""


def parse(text):
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result
