def parse(text):
    return dict(s.split(' = ', 1) for s in text.split('\n') if s)
