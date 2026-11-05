import os, sys, argparse, tomllib, tempfile, shutil, shlex
from . import kernel
from ._kernel.core import _safe, _write_json, _read_json, _copy_into
from ._kernel.recipe import _inputs
from ._kernel.run import sandbox, _run, _scrub_env

def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv);extra=[]
    if '--' in argv:i=argv.index('--');extra=argv[i+1:];argv=argv[:i]
    ap=argparse.ArgumentParser(description='run strip ls --accept-generated --signed-only --no-sandbox')
    ap.add_argument('verb',choices=['run','strip','ls']);ap.add_argument('claims',nargs='+')
    for flag in ('accept-generated','signed-only','no-sandbox'):ap.add_argument('--'+flag,action='store_true')
    a=ap.parse_args(argv)
    try:
        for raw in a.claims:
            d=os.path.abspath(raw);r=kernel.load_recipe(d);outs=kernel.generated_outputs(r)
            for s in r.get('step',[]):_safe(d,s['output'])
            state=os.path.join(d,'.launcher','state.json')
            if a.verb=='strip':
                for n in outs:
                    p=_safe(d,n)
                    if os.path.isfile(p):os.unlink(p)
                shutil.rmtree(os.path.join(d,'.launcher'),ignore_errors=True);continue
            if a.verb=='ls':
                v=kernel.verify(d);print(v['name'],v['root'][:12],kernel.phase(d),'materialized' if all(os.path.isfile(_safe(d,n)) for n in outs) else 'latent');continue
            if 'package.toml' not in _inputs(r,d):raise kernel.ClaimError('package.toml must be a pinned input')
            try:
                with open(_safe(d,'package.toml'),'rb') as f:entry=tomllib.load(f)['package']['entrypoint']
            except (OSError,ValueError,KeyError) as e:raise kernel.ClaimError('invalid package.toml: '+str(e))
            _safe(d,entry);phase=kernel.phase(d)
            if a.signed_only and phase!='signed':print('signed trust required',file=sys.stderr);return 5
            if not all(os.path.isfile(_safe(d,n)) for n in outs):
                producer=os.environ.get('RETICULI_PRODUCER')
                if not producer:print('latent: set RETICULI_PRODUCER',file=sys.stderr);return 7
                with tempfile.TemporaryDirectory() as tmp:
                    room=os.path.join(tmp,'room');kernel.rebuild(d,producer,room)
                    for n in outs:_copy_into(_safe(room,n),d,n)
                _write_json(state,{'fresh':True})
            st=_read_json(state) if os.path.isfile(state) else {}
            bd=kernel.build_digest(d)
            if st.get('digest') and st['digest']!=bd:print('drifted build; strip to recover',file=sys.stderr);return 6
            if not kernel.audit(d)['ok']:print('audit failed; strip to recover',file=sys.stderr);return 6
            if st.get('fresh') and not a.accept_generated:print('fresh bytes: pass --accept-generated',file=sys.stderr);return 4
            if a.accept_generated:_write_json(state,{'fresh':False,'digest':bd})
            cmd=shlex.join([sys.executable,entry]+extra)
            if a.no_sandbox:
                scratch=os.path.join(d,'.launcher','scratch');os.makedirs(scratch,exist_ok=True)
                out=_run(['/bin/sh','-c',cmd],d,_scrub_env({'HOME':scratch,'TMPDIR':scratch}),3600);b='off'
            else:out,b=sandbox(cmd,d,timeout=3600)
            print(f'{phase}; quarantine = "{b}"',file=sys.stderr)
            sys.stdout.write(out['stdout']);sys.stderr.write(out['stderr']);return out['returncode']
        return 0
    except kernel.ClaimError as e:print(str(e),file=sys.stderr);return 3
if __name__=='__main__':sys.exit(main())
