"""Formal gate for quirkcalc's cousin `clamp` — PROVE, don't sample or bound.

The bounded-exhaustive gate decided `impl == reference` over a finite domain,
trusting the reference. This proves `impl` satisfies a DECLARATIVE spec over ALL
integers, trusting only the checker (z3). Two ceilings lifted at once: the domain
is unbounded (every integer, not a sample and not an enumerated frontier), and
there is no reference implementation to trust — only the spec predicate.

Soundness of the obligation: the gate builds the proof obligation FROM the
implementation's own AST, so a producer cannot pass by supplying a fake model —
it must actually write a clamp the translator can render and z3 can prove. The
implementation language is deliberately restricted (straight-line integer
arithmetic, comparisons, min/max/abs, conditional expressions — NO division, NO
loops), which is exactly the fragment where Python's unbounded-int semantics and
SMT `Int` coincide, so the AST->SMT translation is faithful and small enough to
audit. A correct impl outside that fragment is refused, not blessed — the basin
is "impls the gate can prove," narrower than "impls that are correct," and that
narrowing is the price of proof.

Stdlib only (shells out to the `z3` binary). Writes PROVEN iff z3 returns unsat.
"""
import ast
import subprocess
import sys

sys.path.insert(0, ".")
import spec

_BIN = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*"}
_CMP = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "="}


def to_smt(node):
    """Translate one restricted-language expression node to an SMT-LIB2 term."""
    if isinstance(node, ast.Name):
        if node.id not in spec.PARAMS:
            raise ValueError(f"unknown name: {node.id}")
        return node.id
    if isinstance(node, ast.Constant) and isinstance(node.value, int) \
            and not isinstance(node.value, bool):
        return str(node.value) if node.value >= 0 else f"(- {-node.value})"
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        return f"({_BIN[type(node.op)]} {to_smt(node.left)} {to_smt(node.right)})"
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return f"(- {to_smt(node.operand)})"
    if isinstance(node, ast.IfExp):                       # a if c else b -> (ite c a b)
        return f"(ite {to_smt(node.test)} {to_smt(node.body)} {to_smt(node.orelse)})"
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        op = node.ops[0]
        a, b = to_smt(node.left), to_smt(node.comparators[0])
        if isinstance(op, ast.NotEq):
            return f"(distinct {a} {b})"
        return f"({_CMP[type(op)]} {a} {b})"
    if isinstance(node, ast.BoolOp):
        joiner = "and" if isinstance(node.op, ast.And) else "or"
        return f"({joiner} {' '.join(to_smt(v) for v in node.values)})"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        args = [to_smt(a) for a in node.args]
        if node.func.id == "min" and len(args) == 2:
            return f"(ite (<= {args[0]} {args[1]}) {args[0]} {args[1]})"
        if node.func.id == "max" and len(args) == 2:
            return f"(ite (>= {args[0]} {args[1]}) {args[0]} {args[1]})"
        if node.func.id == "abs" and len(args) == 1:
            return f"(ite (>= {args[0]} 0) {args[0]} (- {args[0]}))"
    raise ValueError(f"unsupported construct in impl: {ast.dump(node)}")


def impl_term(path):
    """The impl must be a single `def FUNC(params): return <expr>` (a docstring is
    allowed). We translate its one returned expression; anything else is refused."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    fn = next((n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == spec.FUNC), None)
    if fn is None:
        raise ValueError(f"no function {spec.FUNC}")
    stmts = [s for s in fn.body
             if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    if len(stmts) != 1 or not isinstance(stmts[0], ast.Return):
        raise ValueError("impl must be a single return of an expression")
    return to_smt(stmts[0].value)


def main():
    try:
        term = impl_term(spec.FUNC + ".py")
    except (OSError, ValueError) as e:
        print(f"formal: cannot form a proof obligation from the impl: {e}")
        sys.exit(1)
    smt = (
        "".join(f"(declare-const {p} Int)" for p in spec.PARAMS)
        + f"(define-fun result () Int {term})"
        + f"(assert {spec.PRECONDITION})"
        + "(assert (not (and " + " ".join(spec.properties("result")) + ")))"
        + "(check-sat)(get-model)"
    )
    r = subprocess.run(["z3", "-in"], input=smt, capture_output=True, text=True, check=False)
    out = r.stdout.strip()
    if out.startswith("unsat"):
        print(f"formal: z3 proved {spec.FUNC} satisfies the spec for ALL integers "
              "(unsat: the spec cannot be violated)")
        with open("PROVEN", "w", encoding="utf-8") as f:
            f.write("proven")
    elif out.startswith("sat"):
        print(f"formal: z3 REFUTED {spec.FUNC} — a counterexample exists:\n{out}")
        sys.exit(1)
    else:
        print(f"formal: z3 inconclusive: {out or r.stderr.strip()}")
        sys.exit(1)


if __name__ == "__main__":
    main()
