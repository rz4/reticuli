def parse(text):
    result = {}
    for line in text.split("\n"):
        if "=" in line:
            k, v = line.split("=", 1)
            result[k.strip()] = v.strip()
    return result
