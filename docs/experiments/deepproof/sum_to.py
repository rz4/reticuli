def sum_to(n):
    """Sum 0 + 1 + ... + n by an explicit loop (the gate proves the loop)."""
    i = 0
    s = 0
    while i < n:
        i = i + 1
        s = s + i
    return s
