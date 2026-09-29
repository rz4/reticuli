"""Small parser for newline-separated key/value assignments."""


def parse(text):
    """Parse assignments of the form ``key = value`` into a dictionary.

    Values that can be represented as integers are converted to ``int``;
    repeated keys keep the value from their last assignment.
    """
    result = {}
    for line in text.splitlines():
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        try:
            value = int(value)
        except ValueError:
            pass
        result[key] = value
    return result
