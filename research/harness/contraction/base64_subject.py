"""The base64 subject: C_0 (round-trip + RFC 4648 vectors) and the probe set.

Kept as the instrument's regression subject — its fixtures drive the self-test.
"""

from __future__ import annotations

import random

from boundary import Boundary, observe

VECTORS = [
    (b"", ""),
    (b"f", "Zg=="),
    (b"fo", "Zm8="),
    (b"foo", "Zm9v"),
    (b"foob", "Zm9vYg=="),
    (b"fooba", "Zm9vYmE="),
    (b"foobar", "Zm9vYmFy"),
]
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
FUZZER_SEEDS = range(1000)


def _s(x) -> str:
    return x.decode("ascii") if isinstance(x, (bytes, bytearray)) else x


def _roundtrip_samples() -> list[bytes]:
    out = [b"", b"\x00", b"\xff", bytes(range(256))]
    r = random.Random(0)
    for _ in range(64):
        out.append(bytes(r.randrange(256) for _ in range(r.randrange(0, 40))))
    return out


def _happy(impl) -> list[str]:
    fails: list[str] = []
    enc, dec = getattr(impl, "encode", None), getattr(impl, "decode", None)
    if enc is None or dec is None:
        return ["missing encode/decode"]
    for raw, encoded in VECTORS:
        got = observe(enc, raw)
        if got[0] != "ok" or _s(got[1]) != encoded:
            fails.append(f"vector encode({raw!r}) -> {got!r}, want {encoded!r}")
        got_d = observe(dec, encoded)
        if got_d != ("ok", raw):
            fails.append(f"vector decode({encoded!r}) -> {got_d!r}, want {raw!r}")
    for b in _roundtrip_samples():
        e = observe(enc, b)
        if e[0] != "ok":
            fails.append(f"roundtrip encode({b!r}) was rejected")
            continue
        d = observe(dec, _s(e[1]))
        if d != ("ok", b):
            fails.append(f"roundtrip decode(encode({b!r})) -> {d!r}")
    return fails


def C0() -> Boundary:
    return Boundary("base64", op="decode", checks=[_happy])


def _fuzz(seed: int) -> str:
    r = random.Random(seed)
    pool = ALPHABET + "=" + " \n\t" + "-_" + "!@.*"
    return "".join(r.choice(pool) for _ in range(r.randrange(0, 24)))


def probes() -> list[str]:
    wellformed = [enc for _, enc in VECTORS if enc]
    malformed = [
        "Zm 9v", "Zm9v\n", "Zm9vYg ==", "\tZg==", "Zm9v YmFy",
        "Zg", "Zg=", "Zg===", "Zm9vYg", "Zm8",
        "Zm9v!v", "Zg@=", "....",
        "Zm9-Yg==", "Zm9_Yg==", "-_-_",
        "Zh==", "Zm9=", "Zp==",
        "", "Z",
    ]
    seen: dict[str, None] = {}
    for s in wellformed + malformed:
        seen.setdefault(s, None)
    for seed in FUZZER_SEEDS:
        seen.setdefault(_fuzz(seed), None)
    return list(seen)
