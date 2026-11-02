"""Reference (M1), from scratch (no stdlib shortcut): core glob, passes the
boundary. Generated/excluded from the root; the producer never sees it."""
def match(pattern, name):
    import re
    i = 0; rx = ["(?s)"]
    while i < len(pattern):
        c = pattern[i]
        if c == "*": rx.append(".*")
        elif c == "?": rx.append(".")
        elif c == "[":
            j = i + 1
            if j < len(pattern) and pattern[j] == "!": j += 1
            if j < len(pattern) and pattern[j] == "]": j += 1
            while j < len(pattern) and pattern[j] != "]": j += 1
            if j >= len(pattern): rx.append(re.escape(c))
            else:
                stuff = pattern[i+1:j].replace("\\", "\\\\")
                if stuff.startswith("!"): stuff = "^" + stuff[1:]
                rx.append("[" + stuff + "]"); i = j
        else: rx.append(re.escape(c))
        i += 1
    rx.append(r"\Z")
    return re.match("".join(rx), name) is not None
