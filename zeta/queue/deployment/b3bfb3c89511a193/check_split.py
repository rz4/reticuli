import json, sys
sys.dont_write_bytecode = True
from pathlib import Path

here = Path(__file__).resolve().parent
sys.path.insert(0, str(here))
from _zeta import split as splitlib

entry = json.loads((here / "entry.json").read_text())
claimed = entry["split"]
recomputed = splitlib.classify(entry["population"], claimed["pressure"],
                               claimed["observations"], claimed.get("controls"))
# Everything classify decides must re-earn exactly. The two reduction fields
# are about which witnesses were collapsed onto this one, not about the
# classification, so they are checked for shape instead.
for key, value in recomputed.items():
    if claimed.get(key) != value:
        raise SystemExit(f"split did not re-earn: {key}")
if claimed["pressure"]["id"] not in claimed["witnessed_by"]:
    raise SystemExit("retained witness is not among the witnesses it stands for")
if claimed["witness_count"] != len(claimed["witnessed_by"]):
    raise SystemExit("witness count does not match the witness list")
if entry["lane"] != claimed["lane"] or entry["disposition"] != claimed["disposition"]:
    raise SystemExit("entry header disagrees with its own split")
Path("SPLIT_OK").write_text("ok\n")
