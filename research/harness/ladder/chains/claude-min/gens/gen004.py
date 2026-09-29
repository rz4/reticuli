def parse(text):
    result = {}
    for line in text.split("\n"):
        k, sep, v = line.partition("=")
        if sep:
            result[k.strip()] = v.strip()
    return result
