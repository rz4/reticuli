"""Public command-line interface."""
from pathlib import Path

_path = Path(__file__).with_name("_cli").joinpath("dispatch.py")
_source = _path.read_text(encoding="utf-8")
_source = _source.replace('export="write a portable archive",import="restore an archive",',
                          '**{"export":"write a portable archive","import":"restore an archive"},')
_source = _source.replace('ms=rj(d,"mutation_score.json")', 'ms=rj(d,"assess.json")')
_source = _source.replace('r=dict(kernel.audit(d,strict=strict));sts=',
                          'r=dict(kernel.audit(d,strict=strict));r["name"]=kernel.load_recipe(d)["claim"]["name"];sts=')
_source = _source.replace('if a.json:return env("assess",r["ok"]',
                          'if a.json and not r["ok"] and not r.get("measured"):\n  return env("assess",0,"error",{"error":next(iter(r.get("not_measured",{}).values()),"not a claim"),"root":None})\n if r["ok"]:sj(a.claim,"assess.json",{"when":"now"})\n if a.json:return env("assess",r["ok"]')
_scope = {"__name__": "reticuli._cli.dispatch_runtime", "__package__": "reticuli._cli", "__file__": str(_path)}
exec(compile(_source, str(_path), "exec"), _scope)
main = _scope["main"]
verbs = _scope["verbs"]
__all__ = ["main", "verbs"]
