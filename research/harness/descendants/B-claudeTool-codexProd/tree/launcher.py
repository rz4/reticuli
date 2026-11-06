import os,sys,json,shutil,tempfile,subprocess,argparse,tomllib,shlex
from . import kernel
from ._kernel.recipe import generated_outputs,_inputs
from ._kernel.core import _safe,_write_json
from ._kernel.run import _sandbox_argv,_scrub_env

def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv); extra=[]
    if '--' in argv:
        i=argv.index('--'); extra=argv[i+1:]; argv=argv[:i]
    ap=argparse.ArgumentParser(description='run strip ls --accept-generated --signed-only --no-sandbox')
    ap.add_argument('verb',choices=['run','strip','ls']); ap.add_argument('claims',nargs='+')
    for flag in ('accept-generated','signed-only','no-sandbox'): ap.add_argument('--'+flag,action='store_true')
    a=ap.parse_args(argv)
    try:
        for raw in a.claims:
            d=os.path.abspath(raw); r=kernel.load_recipe(d); gens=generated_outputs(r)
            paths=[_safe(d,p) for p in gens]; state=os.path.join(d,'.launcher','state.json')
            if a.verb=='strip':
                for p in paths:
                    if os.path.exists(p): os.unlink(p)
                shutil.rmtree(os.path.join(d,'.launcher'),ignore_errors=True); continue
            if a.verb=='ls':
                print(r['claim']['name'],kernel.verify(d)['root'][:12],kernel.phase(d),'materialized' if all(os.path.isfile(p) for p in paths) else 'latent'); continue
            if 'package.toml' not in _inputs(r,d): raise kernel.ClaimError('package.toml must be a pinned input')
            with open(_safe(d,'package.toml'),'rb') as f: pkg=tomllib.load(f)
            entry=_safe(d,pkg['package']['entrypoint'])
            if a.signed_only and kernel.phase(d)!='signed': print('signed claim required',file=sys.stderr); return 5
            if not all(os.path.isfile(p) for p in paths):
                producer=os.environ.get('RETICULI_PRODUCER')
                if not producer: print('latent: configure RETICULI_PRODUCER',file=sys.stderr); return 7
                with tempfile.TemporaryDirectory() as tmp:
                    room=os.path.join(tmp,'room'); kernel.rebuild(d,producer,room)
                    for p in gens:
                        os.makedirs(os.path.dirname(_safe(d,p)),exist_ok=True); shutil.copy2(_safe(room,p),_safe(d,p))
                _write_json(state,{'fresh':True})
            try: saved=json.load(open(state))
            except OSError: saved={}
            if saved.get('build') and saved['build']!=kernel.build_digest(d): print('drifted build; strip to recover',file=sys.stderr); return 6
            if saved.get('fresh') and not a.accept_generated: print('new bytes require --accept-generated',file=sys.stderr); return 4
            if not kernel.audit(d)['ok']: print('audit failed; strip to recover',file=sys.stderr); return 6
            if a.accept_generated: _write_json(state,{'build':kernel.build_digest(d),'fresh':False})
            cmd=shlex.join([sys.executable,entry]+extra); args,b=_sandbox_argv(cmd,d)
            if a.no_sandbox: args=['/bin/sh','-c',cmd]; b='off'
            scratch=os.path.join(d,'.launcher','scratch'); os.makedirs(scratch,exist_ok=True)
            e=_scrub_env({'HOME':scratch,'TMPDIR':scratch})
            if b in ('seatbelt','bubblewrap'): e['RETICULI_JAILED']=b
            print(kernel.phase(d)+f' quarantine = "{b}"',file=sys.stderr)
            return subprocess.run(args,cwd=d,env=e).returncode
        return 0
    except (kernel.ClaimError,OSError,ValueError,KeyError) as e: print(str(e),file=sys.stderr); return 3
if __name__=='__main__': sys.exit(main())
