"""Carve S_0: the evaluation-core slice, by the preregistered mechanical
rule — 'the case drives only the evaluator'. Excludes regex, dates,
I/O/env, modules, limit-free-running edge drivers noted below, and the
phase-0 harness artifacts (cases reference jq itself fails under the
plain runner)."""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "baseline"))
from run_baseline import parse_cases  # the same parser: one corpus reading

EXCLUDE = re.compile(
    r"\b(test|match|capture|scan|splits|sub|gsub)\s*\(|"      # regex
    r"\b(strftime|strptime|mktime|gmtime|localtime|now|date|todate|fromdate|dateadd|datesub)\b|"  # dates
    r"\b(input|inputs|debug|stderr|input_line_number|\$ENV|env)\b|"    # io/env
    r"\b(import|include|modulemeta|get_search_list)\b|"       # modules
    r"\$__prog__|halt|getpath\(\s*env"                        # misc drivers
)
cases = parse_cases(os.path.join(HERE, "corpus", "jq-1.8.1.test"))
baseline = {r["i"]: r for r in json.load(open(os.path.join(HERE, "baseline", "baseline.json")))}
kept, dropped = [], {"pattern": 0, "harness": 0}
for i, c in enumerate(cases):
    if baseline.get(i, {}).get("jq") != "pass":
        dropped["harness"] += 1; continue
    if EXCLUDE.search(c["program"]):
        dropped["pattern"] += 1; continue
    kept.append(c)
out = os.path.join(HERE, "corpus", "s0-eval-core.test")
with open(out, "w") as f:
    for c in kept:
        f.write(c["program"] + "\n" + c["input"] + "\n")
        for e in c["expect"]: f.write(e + "\n")
        f.write("\n")
print(f"S_0 carved: {len(kept)} cases kept; dropped {dropped}")
