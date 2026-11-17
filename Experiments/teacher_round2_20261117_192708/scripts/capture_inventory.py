"""Inventory all successful and quarantined physical captures without visual verdicts."""
import json,sys,datetime as dt,platform
from pathlib import Path
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1];sys.path.insert(0,str(ROOT/'Tools/ActionEncoder'))
from review_evidence import file_hash
import torch
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
quarantine=set(read(R/'reports/capture_quarantine.json')['quarantined_ids'])
items=[]
for name in ['pilot','main','fixpilot','fixmain']:
    done=read(R/f'{name}_done.json');assert done['finished'] and done['failed']==0
    assert done['completed']==done['total']==len(done['items'])
    for item in done['items']:
        assert item['ok'];cid=item['candidate_id'];path=R/'observations'/cid/'observation_manifest.json';obs=read(path)
        items.append({'candidate_id':cid,'batch':name,'technical_quarantine':cid in quarantine,'observation_manifest_sha256':file_hash(path),'frames':obs['source_frame_count'],'pages':len(obs['contact_sheets'])})
assert len(items)==72 and len({x['candidate_id'] for x in items})==72
report={'created_at':dt.datetime.now(dt.timezone.utc).isoformat(),'captures':72,'capture_failures':0,'technical_quarantined':len(quarantine),'new_final_capture_candidates':36,'all_frames':sum(x['frames'] for x in items),'all_pages':sum(x['pages'] for x in items),'physical_inventory_only':True,'items':items}
with (R/'reports/capture_inventory.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
env={'python':sys.version,'python_executable':sys.executable,'pytorch':torch.__version__,'platform':platform.platform(),'planned_training_threads':2,'source_hashes':{p.name:file_hash(p) for p in (ROOT/'Tools/ActionEncoder').glob('*.py')},'training_not_started_by_this_script':True}
with (R/'reports/environment_before_training.json').open('x',encoding='utf-8') as f:json.dump(env,f,ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in report.items() if k!='items'}))
