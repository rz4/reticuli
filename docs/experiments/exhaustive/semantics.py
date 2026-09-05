"""quirkcalc — a small integer expression evaluator. The operator set and its
precedence/associativity are non-standard; the behavior is defined entirely by
the test suite. This is one implementation of that behavior."""


class CalcError(Exception):
    pass


# operator -> (precedence, associativity); higher precedence binds tighter
_OPS = {
    "~": (4, "L"),
    "*": (3, "L"), "/": (3, "R"),
    "?": (2, "L"), "%": (2, "L"),
    "+": (1, "L"), "-": (1, "R"),
}


def _tokenize(s):
    toks, i = [], 0
    while i < len(s):
        c = s[i]
        if c.isspace():
            i += 1
        elif c.isdigit():
            j = i
            while j < len(s) and s[j].isdigit():
                j += 1
            toks.append(("num", int(s[i:j])))
            i = j
        elif c in _OPS or c in "()":
            toks.append((c, None))
            i += 1
        else:
            raise CalcError(f"bad character: {c!r}")
    return toks


def _apply(op, a, b):
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        if b == 0:
            raise CalcError("division by zero")
        q = abs(a) // abs(b)
        return -q if (a < 0) != (b < 0) else q
    if op == "~":
        try:
            return int(str(a) + str(b))
        except ValueError:
            raise CalcError("digit-join needs a non-negative right operand") from None
    if op == "?":
        return max(a, b)
    if op == "%":
        return (a + b) // 2
    raise CalcError(f"unknown operator: {op}")


class _Parser:
    def __init__(self, toks):
        self.toks, self.i = toks, 0

    def _peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def _next(self):
        t = self._peek()
        self.i += 1
        return t

    def parse(self):
        if not self.toks:
            raise CalcError("empty expression")
        v = self._expr(1)
        if self.i != len(self.toks):
            raise CalcError("trailing tokens")
        return v

    def _atom(self):
        kind, val = self._next()
        if kind == "num":
            return val
        if kind == "(":
            v = self._expr(1)
            k2, _ = self._next()
            if k2 != ")":
                raise CalcError("expected )")
            return v
        raise CalcError(f"unexpected token: {kind}")

    def _expr(self, min_prec):
        left = self._atom()
        while True:
            kind, _ = self._peek()
            if kind not in _OPS:
                break
            prec, assoc = _OPS[kind]
            if prec < min_prec:
                break
            self._next()
            next_min = prec + 1 if assoc == "L" else prec
            left = _apply(kind, left, self._expr(next_min))
        return left


def evaluate(expr):
    return _Parser(_tokenize(expr)).parse()
