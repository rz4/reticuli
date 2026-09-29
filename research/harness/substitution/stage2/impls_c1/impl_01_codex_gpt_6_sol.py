"""Parse newline-separated key = value assignments."""


def parse(text):
    result = {}
    for line in text.splitlines():
        key, value = (part.strip() for part in line.split("=", 1))
        try:
            value = int(value)
        except ValueError:
            pass
        result[key] = value
    return result
