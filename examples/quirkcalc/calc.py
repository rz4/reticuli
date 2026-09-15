"""quirkcalc — an integer expression evaluator with invented semantics.

The operator set, precedence, and associativity exist nowhere but the case
corpus; this file is free water under that claim. The rules, for the reader
(the cases are the authority):

- precedence, loosest to tightest:  + -   <   ? %   <   * /   <   ~
- `~` digit-join: 12 ~ 34 -> 1234; a negative RIGHT operand raises CalcError
- `?` max, `%` floor-average (a+b)//2; their level is LEFT-associative
- the additive and multiplicative levels are RIGHT-associative
  (10 - 3 - 2 -> 9;  100 / 5 / 2 -> 50)
- `/` truncates toward zero ((0-7)/2 -> -3); division by zero raises CalcError
- literals are non-negative integers; parentheses group
"""


class CalcError(Exception):
    pass


def _tokens(s):
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c.isspace():
            i += 1
        elif c.isdigit():
            j = i
            while j < len(s) and s[j].isdigit():
                j += 1
            out.append(int(s[i:j]))
            i = j
        elif c in "+-*/~?%()":
            out.append(c)
            i += 1
        else:
            raise CalcError(f"bad character {c!r}")
    return out


class _Parser:
    def __init__(self, toks):
        self.toks = toks
        self.i = 0

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else None

    def take(self):
        t = self.peek()
        self.i += 1
        return t

    def expr(self):                       # + -  : right-associative
        left = self.avg()
        if self.peek() in ("+", "-"):
            op = self.take()
            right = self.expr()
            return left + right if op == "+" else left - right
        return left

    def avg(self):                        # ? %  : left-associative
        left = self.mul()
        while self.peek() in ("?", "%"):
            op = self.take()
            right = self.mul()
            left = max(left, right) if op == "?" else (left + right) // 2
        return left

    def mul(self):                        # * /  : right-associative
        left = self.join()
        if self.peek() in ("*", "/"):
            op = self.take()
            right = self.mul()
            if op == "*":
                return left * right
            if right == 0:
                raise CalcError("division by zero")
            q = abs(left) // abs(right)   # truncate toward zero
            return q if (left >= 0) == (right >= 0) else -q
        return left

    def join(self):                       # ~    : tightest, left-associative
        left = self.atom()
        while self.peek() == "~":
            self.take()
            right = self.atom()
            if right < 0:
                raise CalcError("digit-join of a negative right operand")
            left = int(str(left) + str(right))
        return left

    def atom(self):
        t = self.take()
        if isinstance(t, int):
            return t
        if t == "(":
            v = self.expr()
            if self.take() != ")":
                raise CalcError("unbalanced parenthesis")
            return v
        raise CalcError(f"unexpected token {t!r}")


def evaluate(expr):
    p = _Parser(_tokens(expr))
    v = p.expr()
    if p.peek() is not None:
        raise CalcError(f"trailing input at {p.peek()!r}")
    return v
