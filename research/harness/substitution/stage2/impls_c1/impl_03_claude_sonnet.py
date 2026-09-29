def parse(text):
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        try:
            value = int(value)
        except ValueError:
            pass
        result[key] = value
    return result
