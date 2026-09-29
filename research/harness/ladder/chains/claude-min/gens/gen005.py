def parse(text):
    return dict(
        (k.strip(), v.strip())
        for k, sep, v in (line.partition("=") for line in text.split("\n"))
        if sep
    )
