parse = lambda text: dict(line.split(' = ', 1) for line in text.splitlines() if line)
