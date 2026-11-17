"""Explicit one-shot launch with a persistent per-round claim and captured output."""
import datetime as dt,json,os,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1]
def now():return dt.datetime.now(dt.timezone.utc).isoformat()
manifest=R/'frozen_snapshot/manifest.json';out=R/'checkpoint_epoch20'
assert manifest.is_file() and not out.exists()
command=[sys.executable,str(ROOT/'Tools/ActionEncoder/retrain_and_eval.py'),'train','--snapshot-manifest',str(manifest),'--out-dir',str(out),'--epochs','20','--batch-size','32','--threads','2']
claim={'status':'launching','started_at':now(),'pid':os.getpid(),'command':command,'release_approved':False}
lock=R/'training_claim.json'
with lock.open('x',encoding='utf-8') as f:json.dump(claim,f,indent=2)
try:
    with (R/'reports/training_stdout.log').open('x',encoding='utf-8') as log:
        env=dict(os.environ,PYTHONIOENCODING='utf-8',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
        process=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',env=env)
        claim.update(status='training',trainer_pid=process.pid)
        lock.write_text(json.dumps(claim,indent=2),encoding='utf-8')
        for line in process.stdout:
            log.write(line);log.flush();print(line,end='',flush=True)
        code=process.wait()
    claim.update(status='completed' if code==0 else 'failed',exit_code=code,finished_at=now())
except BaseException as e:
    claim.update(status='failed',error=repr(e),finished_at=now());raise
finally:lock.write_text(json.dumps(claim,indent=2),encoding='utf-8')
sys.exit(code)
