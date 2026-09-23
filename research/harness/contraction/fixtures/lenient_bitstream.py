"""From scratch, lenient: decodes a sextet bitstream and silently ignores every
character that is not in the alphabet (whitespace, padding, junk alike)."""

_A = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_IDX = {ch: i for i, ch in enumerate(_A)}


def encode(b: bytes) -> str:
    out = []
    for i in range(0, len(b), 3):
        chunk = b[i:i + 3]
        pad = 3 - len(chunk)
        v = int.from_bytes(chunk + bytes(pad), "big")
        quad = [_A[(v >> 18) & 63], _A[(v >> 12) & 63], _A[(v >> 6) & 63], _A[v & 63]]
        for k in range(4 - pad, 4):
            quad[k] = "="
        out.append("".join(quad))
    return "".join(out)


def decode(s: str) -> bytes:
    bits = nbits = 0
    out = bytearray()
    for ch in s:
        if ch not in _IDX:
            continue
        bits = (bits << 6) | _IDX[ch]
        nbits += 6
        if nbits >= 8:
            nbits -= 8
            out.append((bits >> nbits) & 0xFF)
    return bytes(out)
