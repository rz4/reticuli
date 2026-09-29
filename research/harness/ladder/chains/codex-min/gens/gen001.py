def parse(text):
    return dict(line.split(" = ", 1) for line in text.splitlines() if line)
