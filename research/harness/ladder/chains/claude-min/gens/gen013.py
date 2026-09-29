def parse(text):
    return {k.strip(): v.strip() for k, v in (line.split("=", 1) for line in text.split("\n") if "=" in line)}
