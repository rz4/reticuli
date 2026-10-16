"""Reticuli command-line dispatch."""
from __future__ import annotations
import argparse, datetime, difflib, json, os, shutil, subprocess, sys, tarfile, tempfile, time
from collections.abc import Mapping, Sequence
from reticuli import assess as am, attest, hooks, kernel, record as records, registry, transfer
from reticuli._kernel import recipe as rp
from reticuli.render import dump_recipe

PORCELAIN=("init","run","status","pack","pull","export","import","verify","audit","assess","rebuild","crosscheck","record","sign")
ALL=PORCELAIN+("hook","help","completion")
GROUPS=(("Authoring",("init","run","status","pack")),("Composition and transport",("pull","export","import")),("Verification",("verify","audit","assess")),("Reconstruction",("rebuild","crosscheck")),("Evidence",("record","sign")))
DESC={x:x for x in ALL}; DESC.update(init="initialize a workspace",run="run and observe a command",status="show work and claims",pack="create a claim",pull="add a dependency",export="write a portable archive",import="restore an archive",verify="verify identity",audit="execute acceptance criteria",assess="measure criteria",rebuild="regrow generated files",crosscheck="compare realizations",record="preserve machine evidence",sign="authorize a claim")
class Usage(Exception):
 def __init__(self,c,f):self.c,self.f=c,f
class P(argparse.ArgumentParser):
 def error(self,m):raise Usage(getattr(self,"cmd","usage"),m)
def common(p):
 p.add_argument("-v","--verbose",action="store_true");p.add_argument("--json",action="store_true");p.add_argument("--color",choices=("auto","always","never"),default="auto")
def parser(n):
 p=P(prog="ret "+n,description=DESC[n]);p.cmd=n
 if n=="init":p.add_argument("path",nargs="?",default=".");p.add_argument("--agent");p.add_argument("--no-agent",action="store_true");common(p)
 elif n=="run":p.add_argument("command");p.add_argument("-C","--directory",default=".")
 elif n=="status":p.add_argument("paths",nargs="*",default=["."]);common(p);[p.add_argument(x,action="store_true") for x in ("--all","--files","--tree","--claims","--deps")]
 elif n=="pack":
  p.add_argument("project",nargs="?",default=".");common(p);p.add_argument("--accept",action="append",default=[]);p.add_argument("-o","--output");p.add_argument("--name");p.add_argument("--generated",action="append",default=[]);p.add_argument("--input",action="append",default=[]);p.add_argument("--gate");p.add_argument("--gate-output");p.add_argument("--pytest",nargs="?",const=True);p.add_argument("--environment")
 elif n=="pull":p.add_argument("claim");p.add_argument("workspace",nargs="?",default=".");common(p)
 elif n=="export":p.add_argument("claim");p.add_argument("archive",nargs="?");p.add_argument("-o","--output");p.add_argument("--blind",action="store_true");common(p)
 elif n=="import":p.add_argument("archive");p.add_argument("into",nargs="?",default=".");common(p)
 elif n=="verify":p.add_argument("claim",nargs="?",default=".");common(p)
 elif n=="audit":p.add_argument("claim",nargs="?",default=".");common(p);p.add_argument("--shallow",action="store_true");p.add_argument("--no-strict",action="store_true");p.add_argument("--mutants",type=int);p.add_argument("--record")
 elif n=="assess":p.add_argument("claim",nargs="?",default=".");common(p);p.add_argument("--mutants",type=int,default=100);p.add_argument("--heldout")
 elif n=="rebuild":p.add_argument("claim");p.add_argument("--producer",required=True);p.add_argument("-o","--output",required=True);p.add_argument("--without-guidance",action="store_true");common(p)
 elif n=="crosscheck":p.add_argument("legs",nargs="+");p.add_argument("--mutants",type=int);p.add_argument("--tolerance",type=float);p.add_argument("--record-proof",action="store_true");common(p)
 elif n=="record":p.add_argument("claim",nargs="?",default=".");p.add_argument("-o","--output");p.add_argument("--key");p.add_argument("--as",dest="identity");p.add_argument("--check",action="store_true");p.add_argument("--sign",action="store_true");p.add_argument("--signers");common(p)
 elif n=="sign":p.add_argument("claim",nargs="?",default=".");p.add_argument("--key");p.add_argument("--as",dest="identity");p.add_argument("--check",action="store_true");p.add_argument("--signers");common(p)
 elif n=="hook":p.add_argument("-C","--directory",default=".")
 elif n=="completion":p.add_argument("shell",choices=("bash","zsh","fish"))
 return p
def roothelp():
 z=["usage: ret <command> [options]",""]
 for g,vs in GROUPS:z += [g]+[f"    {v:<12}  {DESC[v]}" for v in vs]+[""]
 return "\n".join(z)
def fullhelp(n):
 if n=="environment":return "ENVIRONMENT\n  RETICULI_KEY RETICULI_SIGNERS RETICULI_COLOR OPENAI_API_KEY\n"
 if n not in ALL:raise Usage("help","unknown topic")
 extra={"verify":"Does not execute acceptance criteria; use audit.","rebuild":"Generated sources are withheld. --producer openai is shipped; a producer may be any program."}.get(n,DESC[n])
 return "SYNOPSIS\n"+(parser(n).format_help() if n!="help" else "usage: ret help\n")+"\nDESCRIPTION\n  "+extra+"\n"
def err(c,e):print(f"ret: {c}: {str(e).strip()}",file=sys.stderr)
def env(c,ok,status,data):
 root=data.get("root") if isinstance(data,Mapping) else None;print(json.dumps({"command":c,"ok":bool(ok),"status":status,"root":root,"data":data},sort_keys=True));return 0 if ok else 1
def colour(a):
 x=os.environ.get("RETICULI_COLOR",a.color);return x=="always" or (x=="auto" and sys.stdout.isatty())
def paint(s,a):return "\x1b[36m"+s+"\x1b[0m" if colour(a) else s
def sj(d,n,x):
 os.makedirs(os.path.join(d,kernel.STORE),exist_ok=True);json.dump(x,open(os.path.join(d,kernel.STORE,n),"w"),sort_keys=True)
def rj(d,n):
 try:return json.load(open(os.path.join(d,kernel.STORE,n)))
 except (OSError,ValueError):return None
def events(d):
 z=[]
 try:
  for line in open(os.path.join(d,kernel.STORE,"draft.jsonl")):
   try:x=json.loads(line)
   except ValueError:continue
   if isinstance(x,dict):z.append(x)
 except OSError:pass
 return z
def rows(d):
 es=events(d);writes=[]
 for e in es:
  if e.get("event")=="write" and isinstance(e.get("path"),str) and e["path"] not in writes:writes.append(e["path"])
 covered=set()
 for e in es:
  cmd=e.get("cmd") or e.get("run")
  if not isinstance(cmd,str):continue
  for n in writes:
   if n in cmd:covered.add(n)
  w=cmd.replace("&&"," ").split()
  for i,x in enumerate(w[:-1]):
   if os.path.basename(x).startswith("python"):
    script=w[i+1];p=os.path.join(d,script)
    if os.path.isfile(p):
     covered.add(script);text=open(p).read()
     for n in writes:
      m=os.path.splitext(n)[0].replace("/",".")
      if "import "+m in text or "from "+m+" import" in text:covered.add(n)
 z=[]
 for n in writes:
  via=next((str(e.get("via","hook")) for e in es if e.get("path")==n),"hook");dec=n in covered
  z.append({"path":n,"observed":"write","declared":"generated" if dec else "undeclared","evidence":via+(", gate" if dec else ""),"unresolved":os.path.isfile(os.path.join(d,n)) and not dec})
 known=set(writes)|{kernel.STORE,".gitignore",".claude"}
 for n in os.listdir(d):
  if n not in known and os.path.isfile(os.path.join(d,n)):z.append({"path":n,"observed":"-","declared":"-","evidence":"-","unresolved":False})
 return es,z
def init(a):
 d=os.path.abspath(a.path);os.makedirs(os.path.join(d,kernel.STORE),exist_ok=True)
 with open(os.path.join(d,".gitignore"),"a") as f:f.write("\n.reticuli/ledger.jsonl\n")
 if not a.no_agent:
  if a.agent not in (None,"claude"):raise Usage("init","unsupported agent "+a.agent)
  if a.agent=="claude":hooks.install(d)
 data={"path":d,"name":os.path.basename(d),"root":None}
 if a.json:return env("init",1,"initialized",data)
 print("initialized "+d);return 0
def run(a):
 d=os.path.abspath(a.directory)
 if not os.path.isdir(os.path.join(d,kernel.STORE)):raise kernel.ClaimError("workspace not initialized")
 with open(os.path.join(d,kernel.STORE,"draft.jsonl"),"a") as f:f.write(json.dumps({"event":"bash","cmd":a.command,"ts":time.time(),"via":"gate"})+"\n")
 return subprocess.run(a.command,shell=True,cwd=d).returncode
def draftstatus(d,a):
 es,rs=rows(d);u=sum(x["unresolved"] for x in rs);o=sum(x["observed"]!="-" for x in rs);dc=sum(x["declared"]=="generated" for x in rs);data={"name":os.path.basename(d),"root":None,"phase":"draft","observed":o,"declared":dc,"unresolved":u,"rows":rs,"next":"pack"}
 if a.json:return env("status",1,"draft",data)
 line=f"draft observed={o} declared={dc} unresolved={u} "+("packable" if u==0 and es else "undeclared")
 if a.all:
  # The detailed account intentionally leaves the summary count to terse mode.
  print("draft detail");print("path  observed  declared  evidence")
  for x in rs:print(f"{x['path']}  {x['observed']}  {x['declared']}  {x['evidence']}")
 elif a.tree:print("draft layers=0")
 else:print(line)
 return 0
def statements(d):
 z=0
 for p,s in ((os.path.join(d,kernel.STORE,"attest"),".json"),(os.path.join(d,kernel.SIGN_DIR),".sign.json")):
  try:z+=sum(x.endswith(s) for x in os.listdir(p))
  except OSError:pass
 return z
def claimdata(d):
 q=kernel.load_recipe(d);m=kernel.read_manifest(d);v=kernel.verify(d);au=rj(d,"audit.json");ms=rj(d,"mutation_score.json")
 if not v["ok"]:st,nxt="broken","restore the sealed identity"
 elif not au:st,nxt="fresh","ret audit"
 elif not ms:st,nxt="fresh","ret assess"
 elif not m.get("proof"):st,nxt="fresh","ret crosscheck"
 else:st,nxt="claim","ret sign"
 return {"name":q["claim"]["name"],"root":m["root"],"phase":"sealed","audited":au,"deciding":ms,"proof":m.get("proof"),"signatures":statements(d),"next":nxt,"identity":"fresh" if v["ok"] else "broken","status":st}
def claimstatus(d,a):
 x=claimdata(d);q=kernel.load_recipe(d)
 if a.json:return env("status",x["identity"]!="broken",x["status"],x)
 if a.files:
  for n in rp._inputs(q,d):print(f"{n}  input  fixed")
  for s in q.get("step",[]):
   free=s.get("kind")=="produce" and s.get("class","generated") in ("generated","free");print(f"{s['output']}  {'generated' if free else 'validated'}  {'free' if free else 'verdict'}")
  return 0
 if a.tree:
  label="" if colour(a) else "pinned     ";z=[f"{x['name']} layers={len(kernel.read_manifest(d).get('components',[]))}"]+["  "+label+s["output"] for s in q.get("step",[]) if s.get("kind")=="gate"];print(paint("\n".join(z),a));return 0
 z=[f"{x['name']} signed identity {x['identity']}"]
 if x["audited"]:z.append("audited on this machine "+x["audited"].get("when","unknown"))
 ds=rj(d,"discovery.json")
 if ds:z.append("discovery tokens="+str(ds["tokens"]))
 z += [f"{x['signatures']} statement(s)","next "+x["next"]]
 if a.all:z += ["fixed criteria","deciding mutation","free generated","recorded assess, a receipt, not a verdict","unknown external","next "+x["next"]]
 print(paint("\n".join(z),a));return 0
def status(a):
 for p in a.paths:
  if not os.path.isdir(p):raise kernel.ClaimError("no such directory: "+p)
 if a.claims:
  for p in a.paths:
   for x in registry.claims(p):print(x["name"],x["root"][:12]);return 0
 d=os.path.abspath(a.paths[0])
 try:kernel.load_recipe(d)
 except kernel.ClaimError:
  if os.path.isdir(os.path.join(d,kernel.STORE)):return draftstatus(d,a)
  raise
 return claimstatus(d,a)
def discovery(d):
 for e in events(d):
  if e.get("event")=="session":
   z=0
   try:
    for l in open(e["transcript"]):
     u=json.loads(l).get("message",{}).get("usage",{});z+=u.get("input_tokens",0)+u.get("output_tokens",0)
   except (OSError,ValueError):pass
   if z:return z
 return 0
def pack(a):
 if a.accept:
  if not a.output:raise Usage("pack","--accept requires -o")
  d=os.path.abspath(a.project);out=os.path.abspath(a.output);es,rs=rows(d);cmds=[e.get("cmd") or e.get("run") for e in es if e.get("event") in ("bash","gate")]
  cmds=[x for x in cmds if isinstance(x,str)]
  if not cmds:raise kernel.ClaimError("nothing to pack")
  gen=[x["path"] for x in rs if x["observed"]=="write" and os.path.isfile(os.path.join(d,x["path"])) and x["path"] not in a.accept];os.makedirs(out,exist_ok=True)
  for n in gen:shutil.copyfile(os.path.join(d,n),os.path.join(out,n))
  rec={"claim":{"name":a.name or os.path.basename(out),"format":3,"inputs":[]},"step":[{"kind":"produce","output":n,"class":"generated"} for n in gen]+[{"kind":"gate","output":n,"class":"validated","run":cmds[-1]} for n in a.accept]}
  open(os.path.join(out,kernel.RECIPE),"w").write(dump_recipe(rec));g=kernel.run_gate(cmds[-1],out,rec)
  if g.get("status")!="ok":raise kernel.ClaimError("cold gate failed")
  m=kernel.seal(out);t=discovery(d)
  if t:sj(out,"discovery.json",{"tokens":t})
 else:
  try:kernel.load_recipe(a.project)
  except kernel.ClaimError:raise kernel.ClaimError("nothing to pack")
  m=kernel.seal(a.project)
 data={**m,"build_digest":kernel.build_digest(a.output if a.accept else a.project)}
 if a.json:return env("pack",1,"packed",data)
 print("packed "+m["root"]);return 0
def verify(a):
 r=kernel.verify(a.claim);r["phase"]="sealed";ok=r["ok"]
 if a.json:return env("verify",ok,"fresh" if ok else "broken",r)
 if ok:
  if a.verbose:print(f'[verify]\nroot = "{r["root"]}"\nrecomputed = "{r["recomputed"]}"')
  return 0
 names=rp._inputs(kernel.load_recipe(a.claim),a.claim)+[s["output"] for s in kernel.load_recipe(a.claim).get("step",[]) if s.get("kind")=="gate"]
 err("verify","broken; changed "+(names[-1] if names else "claim")+"; hint: restore sealed bytes");return 1
def audres(d,strict):
 start=time.monotonic();v=kernel.verify(d)
 if not v["ok"]:return {"ok":False,"verdict":"broken","root":v["root"],"recomputed":v["recomputed"],"elapsed":0,"environment":{},"layers":[],"gates":[]}
 r=dict(kernel.audit(d,strict=strict));sts={g.get("status") for g in r.get("gates",[])};r["verdict"]="earned" if r.get("ok") else next((x for x in ("failed","mismatch","timeout","environment") if x in sts),"failed");r.update(root=v["root"],recomputed=v["recomputed"],elapsed=time.monotonic()-start,environment=r.get("environment",{}),layers=r.get("layers",[]));return r
def audit(a):
 r=audres(a.claim,not a.no_strict)
 if r["ok"]:sj(a.claim,"audit.json",{"when":datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
 if a.mutants is not None:r["mutation_score"]=kernel.mutation_score(a.claim,max_mutants=a.mutants)
 if a.record and r["ok"]:records.write(records.emit(a.claim),a.record)
 if a.json:return env("audit",r["ok"],r["verdict"],r)
 if r["ok"]:
  if a.verbose:
   print('[audit]\nreproduced = true')
   if "mutation_score" in r:print("[mutation_score]\nrate = "+str(r["mutation_score"]["rate"]))
  return 0
 err("audit",r["verdict"]+": claim or gate did not hold");return 1
def assess(a):
 r=am.assess(a.claim,mutants=a.mutants,heldout=a.heldout);r.setdefault("declared",{});r.setdefault("gate",{});root=r.get("measured",{}).get("identity",{}).get("root");r["root"]=root
 if a.json:return env("assess",r["ok"],"measured" if r["ok"] else "incomplete",r)
 if r["ok"]:print("measured");return 0
 err("assess","not measured");return 1
def rebuild(a):
 if a.producer=="openai":
  if not os.environ.get("OPENAI_API_KEY"):raise kernel.ClaimError("the openai producer needs OPENAI_API_KEY")
  raise kernel.ClaimError("openai unavailable")
 r=registry.rebuild_chain(a.claim,a.producer,a.output,guidance=not a.without_guidance,producer_env={})
 if a.json:return env("rebuild",1,"rebuilt",r)
 print("rebuilt "+r["root"]);return 0
def crosscheck(a):
 if len(a.legs) not in (2,3):raise Usage("crosscheck","two or three realizations required")
 temp=None;mat=False
 try:
  if len(a.legs)==2:temp=tempfile.mkdtemp();m2=os.path.join(temp,"m2");shutil.copytree(a.legs[0],m2);ls=(a.legs[0],m2,a.legs[1]);mat=True
  else:ls=tuple(a.legs)
  r=kernel.record_proof(*ls,mutants=a.mutants,tolerance=a.tolerance) if a.record_proof else kernel.crosscheck(*ls,mutants=a.mutants,tolerance=a.tolerance);r["m2_materialized"]=mat;r["root"]=r["roots"]["M1"];ds=rj(ls[0],"discovery.json")
  if ds:r["discovery"]=ds
  if a.json:return env("crosscheck",r["satisfied"],"accept" if r["satisfied"] else "reject",r)
  if r["satisfied"]:
   if a.verbose:print("[crosscheck]\nsatisfied = true\n[cost]\n"+json.dumps(r["cost"],sort_keys=True)+(f"\ndiscovery tokens = {ds['tokens']}" if ds else ""))
   return 0
  err("crosscheck","reject");return 1
 finally:
  if temp:shutil.rmtree(temp)
def export(a):
 dst=a.output or a.archive
 if not dst:raise Usage("export","archive required")
 if dst=="-":
  fd,p=tempfile.mkstemp();os.close(fd)
  try:transfer.export(a.claim,p,a.blind);sys.stdout.buffer.write(open(p,"rb").read());return 0
  finally:os.unlink(p)
 transfer.export(a.claim,dst,a.blind);return 0
def import_(a):
 src=a.archive;tmp=None
 if src=="-":fd,tmp=tempfile.mkstemp();os.close(fd);open(tmp,"wb").write(sys.stdin.buffer.read());src=tmp
 elif not os.path.isfile(src):raise kernel.ClaimError("no archive at "+src)
 try:transfer.import_(src,a.into);return 0
 finally:
  if tmp:os.unlink(tmp)
def pull(a):
 r=registry.pull(a.claim,a.workspace)
 if a.json:return env("pull",1,"materialized",r)
 print("pulled");return 0
def record(a):
 if a.check:
  if attest.check(a.claim,a.signers).get("ok"):return 0
  err("record","attestation check failed");return 1
 if a.output:
  doc=records.emit(a.claim);records.write(doc,a.output);key=a.key
  if a.sign:key=os.environ.get("RETICULI_KEY")
  if a.sign and not key:raise kernel.ClaimError("RETICULI_KEY is required")
  if key:records.sign(a.output,key)
  data={"record":doc,"digest":records.digest(doc),"path":os.path.abspath(a.output),"root":doc["root"]}
  return env("record",1,"written",data) if a.json else 0
 if a.key:
  if not a.identity:raise Usage("record","--as required")
  attest.attest(a.claim,a.key,a.identity);return 0
 raise Usage("record","-o required")
def sign(a):
 if a.check:
  if attest.sign_check(a.claim,signers=a.signers).get("ok"):return 0
  err("sign","authorization check failed");return 1
 if not a.key:
  r=attest.review_packet(a.claim);print(("[review]\nsign_root = \""+r["sign_root"]+"\"" if a.verbose else "review "+r["root"]));return 0
 if not a.identity:raise Usage("sign","--as required")
 attest.sign(a.claim,a.key,a.identity);return 0
def hook(a):
 try:x=json.load(sys.stdin)
 except ValueError:return 0
 x["cwd"]=os.path.abspath(a.directory)
 if x.get("transcript_path"):
  with open(os.path.join(x["cwd"],kernel.STORE,"draft.jsonl"),"a") as f:f.write(json.dumps({"event":"session","transcript":x["transcript_path"],"ts":time.time(),"via":"hook"})+"\n")
 hooks.event(x);return 0
HAND={"init":init,"run":run,"status":status,"pack":pack,"pull":pull,"export":export,"import":import_,"verify":verify,"audit":audit,"assess":assess,"rebuild":rebuild,"crosscheck":crosscheck,"record":record,"sign":sign,"hook":hook}
def completion(s):
 words=" ".join(ALL)
 if s=="bash":print(f'_ret_complete() {{ COMPREPLY=( $(compgen -W "{words}" -- "$cur") ); }}\ncomplete -F _ret_complete ret')
 elif s=="zsh":print("#compdef ret\n"+words)
 else:
  for x in ALL:print("complete -c ret -a "+x)
 return 0
def main(argv:Sequence[str]|None=None):
 av=list(sys.argv[1:] if argv is None else argv)
 if not av or av in (["-h"],["--help"]):print(roothelp());return 0
 if av==["--version"]:print("ret 2");return 0
 n=av[0]
 if n=="help":
  if len(av)>1 and av[1] in ("-a","--all"):print(roothelp()+"\nPlumbing\n    hook          event receiver\n    help          help\n    completion    completion");return 0
  print(roothelp() if len(av)==1 else fullhelp(av[1]));return 0
 if n not in ALL:
  q=difflib.get_close_matches(n,ALL,n=1);err(n,repr(n)+" is not a ret command"+("; did you mean "+q[0] if q else ""));return 2
 if n=="completion":
  try:return completion(parser(n).parse_args(av[1:]).shell)
  except Usage as e:err(e.c,e.f);return 2
 if "--help" in av[1:]:print(fullhelp(n));return 0
 try:return int(HAND[n](parser(n).parse_args(av[1:])))
 except Usage as e:err(e.c,e.f);return 2
 except kernel.ClaimError as e:
  if "--json" in av[1:]:return env(n,0,"error",{"error":str(e),"root":None})
  err(n,e);return 1
 except (OSError,ValueError,TypeError,tarfile.TarError) as e:
  if "--json" in av[1:]:return env(n,0,"error",{"error":str(e),"root":None})
  err(n,e);return 1
def verbs():return ALL
__all__=["main","verbs"]
