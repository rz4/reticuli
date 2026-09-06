"""Deep-proof gate — total correctness of a LOOP, by machine-checked induction.

The formal gate (clamp) proved a straight-line function: one SMT query, no
induction. Loops need an inductive argument, which a solver will not invent — so
here the CAST must carry its proof: alongside the implementation (`sum_to.py`,
a genuine while-loop in a restricted fragment) the producer supplies `proof.py`
holding a loop INVARIANT and a termination VARIANT. The gate derives the five
Floyd–Hoare verification conditions and z3 discharges each over ALL integers:

  VC1  init         PRE ∧ (state := inits)            ⇒ INVARIANT
  VC2  preserve     PRE ∧ INVARIANT ∧ cond ∧ body     ⇒ INVARIANT'   (induction)
  VC3  post         PRE ∧ INVARIANT ∧ ¬cond           ⇒ POST(return)
  VC4  var-bound    PRE ∧ INVARIANT ∧ cond            ⇒ VARIANT ≥ 0
  VC5  var-decrease PRE ∧ INVARIANT ∧ cond ∧ body     ⇒ VARIANT' < VARIANT

All five unsat (their negations) = the loop is TOTALLY correct: it terminates
and its result satisfies the sealed postcondition, for every input meeting the
precondition. The invariant is the creative content — a correct implementation
with a weak or wrong invariant is REFUSED: the basin is "implementation plus
checkable inductive argument," proof-carrying code in miniature.

Restricted fragment (where Python-int and SMT-Int coincide): the impl is
`def FUNC(params):` then simple `var = expr` initializations, one `while cond:`
whose body is simple assignments, one `return expr`; expressions are integer
arithmetic (+ - *), comparisons, and/or/not, min/max/abs, conditionals — no
division, no nesting, no break. Primed terms are built by sequential
substitution (SSA), and re-binding into the invariant uses SMT-LIB `let`, so no
textual substitution ever touches producer strings. The producer's SMT strings
are token-whitelisted and paren-balanced before use — they cannot inject
commands into the solver script. Stdlib only; shells out to `z3`.
Writes PROVEN iff all five VCs discharge.
"""
import ast
import re
import subprocess
import sys

sys.path.insert(0, ".")
import spec_loop as spec

_BIN = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*"}
_CMP = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "="}


def to_smt(node, env):
    """Restricted expression -> SMT term; names resolve through `env`."""
    if isinstance(node, ast.Name):
        if node.id not in env:
            raise ValueError(f"unknown name: {node.id}")
        return env[node.id]
    if isinstance(node, ast.Constant) and isinstance(node.value, int) \
            and not isinstance(node.value, bool):
        return str(node.value) if node.value >= 0 else f"(- {-node.value})"
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        return f"({_BIN[type(node.op)]} {to_smt(node.left, env)} {to_smt(node.right, env)})"
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return f"(- {to_smt(node.operand, env)})"
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return f"(not {to_smt(node.operand, env)})"
    if isinstance(node, ast.IfExp):
        return (f"(ite {to_smt(node.test, env)} {to_smt(node.body, env)} "
                f"{to_smt(node.orelse, env)})")
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        op = node.ops[0]
        a, b = to_smt(node.left, env), to_smt(node.comparators[0], env)
        if isinstance(op, ast.NotEq):
            return f"(distinct {a} {b})"
        return f"({_CMP[type(op)]} {a} {b})"
    if isinstance(node, ast.BoolOp):
        joiner = "and" if isinstance(node.op, ast.And) else "or"
        return f"({joiner} {' '.join(to_smt(v, env) for v in node.values)})"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        args = [to_smt(a, env) for a in node.args]
        if node.func.id == "min" and len(args) == 2:
            return f"(ite (<= {args[0]} {args[1]}) {args[0]} {args[1]})"
        if node.func.id == "max" and len(args) == 2:
            return f"(ite (>= {args[0]} {args[1]}) {args[0]} {args[1]})"
        if node.func.id == "abs" and len(args) == 1:
            return f"(ite (>= {args[0]} 0) {args[0]} (- {args[0]}))"
    raise ValueError(f"unsupported construct: {ast.dump(node)}")


def _assign(stmt):
    if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)):
        raise ValueError("only simple `var = expr` assignments are allowed")
    return stmt.targets[0].id, stmt.value


def parse_impl(path):
    """The loop shape: inits*, one while, one return. Returns (state order,
    init terms over params, cond builder, body substitution, return builder)."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    fn = next((n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == spec.FUNC), None)
    if fn is None:
        raise ValueError(f"no function {spec.FUNC}")
    if [a.arg for a in fn.args.args] != spec.PARAMS:
        raise ValueError(f"params must be exactly {spec.PARAMS}")
    stmts = [s for s in fn.body
             if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    if len(stmts) < 3 or not isinstance(stmts[-2], ast.While) \
            or not isinstance(stmts[-1], ast.Return):
        raise ValueError("shape must be: initializations, one while loop, one return")
    if stmts[-2].orelse:
        raise ValueError("while-else is not in the fragment")

    params_env = {p: p for p in spec.PARAMS}
    inits, state = {}, []
    for s in stmts[:-2]:
        var, expr = _assign(s)
        if var in params_env or var in inits:
            raise ValueError(f"bad init target: {var}")
        inits[var] = to_smt(expr, params_env)      # inits see params only
        state.append(var)
    if not state:
        raise ValueError("the loop must have state (no initializations found)")

    full_env = {**params_env, **{v: v for v in state}}
    cond = to_smt(stmts[-2].test, full_env)

    subst = dict(full_env)                          # sequential (SSA) body effect
    for s in stmts[-2].body:
        var, expr = _assign(s)
        if var not in state:
            raise ValueError(f"body may only assign state vars: {var}")
        subst[var] = to_smt(expr, subst)
    primed = {v: subst[v] for v in state}

    ret = to_smt(stmts[-1].value, full_env)
    return state, inits, cond, primed, ret


_TOKEN_OK = re.compile(r"^[A-Za-z0-9_+\-*<>=()\s]*$")
_FORBID = ("check", "assert", "declare", "define", "exit", "get", "set",
           "push", "pop", "eval", "let", "!")


def clean_term(s, names, what):
    """The producer's SMT strings are data, not solver commands: whitelist the
    charset, forbid command words, require balanced parens and known symbols."""
    if not isinstance(s, str) or not s.strip():
        raise ValueError(f"{what} must be a non-empty string")
    if not _TOKEN_OK.match(s):
        raise ValueError(f"{what} contains characters outside the fragment")
    low = s.lower()
    for w in _FORBID:
        if w in low:
            raise ValueError(f"{what} may not contain {w!r}")
    depth = 0
    for c in s:
        depth += (c == "(") - (c == ")")
        if depth < 0:
            raise ValueError(f"{what} has unbalanced parentheses")
    if depth != 0:
        raise ValueError(f"{what} has unbalanced parentheses")
    words = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", s))
    known = set(names) | {"and", "or", "not", "ite", "distinct", "true", "false"}
    unknown = words - known
    if unknown:
        raise ValueError(f"{what} uses unknown symbols: {sorted(unknown)}")
    return s.strip()


def relet(term, state, primed):
    """`term` re-read with every state var bound to its primed term — SMT-LIB
    `let` shadows the symbols, so no textual substitution is needed."""
    binds = " ".join(f"({v} {primed[v]})" for v in state)
    return f"(let ({binds}) {term})"


def z3_unsat(label, decls, asserts):
    script = "".join(f"(declare-const {d} Int)" for d in decls) \
        + "".join(f"(assert {a})" for a in asserts) + "(check-sat)(get-model)"
    r = subprocess.run(["z3", "-in"], input=script, capture_output=True,
                       text=True, check=False)
    out = r.stdout.strip()
    if out.startswith("unsat"):
        return True
    print(f"FAILED {label}:")
    print("  " + "\n  ".join(out.splitlines()[:12]) or r.stderr.strip())
    return False


def main():
    try:
        state, inits, cond, primed, ret = parse_impl(spec.FUNC + ".py")
        import proof  # the cast's proof artifact
        names = spec.PARAMS + state
        inv = clean_term(proof.INVARIANT, names, "INVARIANT")
        var = clean_term(proof.VARIANT, names, "VARIANT")
    except (OSError, ValueError, ImportError, AttributeError) as e:
        print(f"deep-proof: cannot form the obligations: {e}")
        sys.exit(1)

    decls = spec.PARAMS + state
    pre = spec.PRECONDITION
    init_eqs = [f"(= {v} {inits[v]})" for v in state]
    vcs = [
        ("VC1 init: the invariant holds on entry",
         [pre, *init_eqs, f"(not {inv})"]),
        ("VC2 preserve: one iteration keeps the invariant (induction)",
         [pre, inv, cond, f"(not {relet(inv, state, primed)})"]),
        ("VC3 post: invariant + exit implies the postcondition",
         [pre, inv, f"(not {cond})",
          f"(not (let ((result {ret})) {spec.POSTCONDITION}))"]),
        ("VC4 variant is bounded below while looping",
         [pre, inv, cond, f"(not (>= {var} 0))"]),
        ("VC5 variant strictly decreases (termination)",
         [pre, inv, cond, f"(not (< {relet(var, state, primed)} {var}))"]),
    ]
    ok = True
    for label, asserts in vcs:
        good = z3_unsat(label, decls, asserts)
        print(("  ✓ " if good else "  ✗ ") + label)
        ok = ok and good
    if not ok:
        sys.exit(1)
    print(f"deep-proof: {spec.FUNC} is TOTALLY correct for all inputs with "
          f"{spec.PRECONDITION} — terminates, and 'result' satisfies "
          f"{spec.POSTCONDITION} (five VCs, each unsat)")
    with open("PROVEN", "w", encoding="utf-8") as f:
        f.write("proven")


if __name__ == "__main__":
    main()
