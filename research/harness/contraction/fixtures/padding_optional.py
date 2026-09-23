"""From scratch, strict on characters, but infers missing '=' padding instead
of rejecting an unpadded string."""

_A = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_IDX = {ch: i for i, ch in enumerate(_A)}


def encode(b: bytes) -> str:
    out = []
    for i in range(0, len(b), 3):
        chunk = b[i:i + 3]
        n = len(chunk)
        v = int.from_bytes(chunk + bytes(3 - n), "big")
        q = [_A[(v >> 18) & 63], _A[(v >> 12) & 63], _A[(v >> 6) & 63], _A[v & 63]]
        if n == 1:
            q[2] = q[3] = "="
        elif n == 2:
            q[3] = "="
        out.append("".join(q))
    return "".join(out)


def decode(s: str) -> bytes:
    if len(s) % 4 == 1:
        raise ValueError("impossible length")
    s = s + "=" * (-len(s) % 4)  # infer the padding the caller left off
    out = bytearray()
    for i in range(0, len(s), 4):
        quad = s[i:i + 4]
        pad = quad.count("=")
        vals = []
        for ch in quad:
            if ch == "=":
                vals.append(0)
            elif ch in _IDX:
                vals.append(_IDX[ch])
            else:
                raise ValueError(f"bad character {ch!r}")
        v = (vals[0] << 18) | (vals[1] << 12) | (vals[2] << 6) | vals[3]
        out += bytes([(v >> 16) & 255, (v >> 8) & 255, v & 255])[:3 - pad]
    return bytes(out)
