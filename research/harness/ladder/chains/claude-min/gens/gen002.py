def parse(text):
    return dict(
        (k.strip(), v.strip())
        for k, v in (line.partition("=")[::2] for line in text.split("\n") if "=" in line)
    )
