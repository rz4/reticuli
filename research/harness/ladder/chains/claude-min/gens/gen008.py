def parse(text):
    return dict(
        map(str.strip, line.split("=", 1))
        for line in text.split("\n")
        if "=" in line
    )
