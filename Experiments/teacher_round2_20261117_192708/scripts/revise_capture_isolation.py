"""Quarantine overlapping cameras, preserve all evidence, re-record same labels as children."""
import json,sys,datetime as dt
from pathlib import Path
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1];sys.path.insert(0,str(ROOT/'Tools/ActionEncoder'))
from review_evidence import file_hash
def jl(p):return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines()]
original=jl(R/'candidates.jsonl');revised=jl(R/'revised_candidates.jsonl')
active={r['parent_candidate_id']:r for r in revised}
parents=[active.get(r['candidate_id'],r) for r in original if r['config']['decision']=='execute']
assert len(parents)==36
children=[]
for parent in parents:
    r=json.loads(json.dumps(parent));pid=r['candidate_id'];base=pid.split('-r')[0]
    cid=base+('-r2' if '-r1' in pid else '-r1')
    r.update(candidate_id=cid,parent_candidate_id=pid)
    r['generation'].update(generated_at=dt.datetime.now(dt.timezone.utc).isoformat(),revision_reason='Same authored text/config; dedicated camera preview scene fixes cross-session visual contamination')
    r['provenance'].update(parent_candidate_id=pid,parent_split='train',parent_semantic_family_id=r['semantic_family_id'],generation_source_file=str(Path(__file__).resolve()),generation_source_sha256=file_hash(__file__))
    children.append(r)
with (R/'revised_candidates_capture.jsonl').open('x',encoding='utf-8') as f:
    for r in children:f.write(json.dumps(r,ensure_ascii=False)+'\n')
report={'created_at':dt.datetime.now(dt.timezone.utc).isoformat(),'status':'technical_quarantine_not_ai_verdict','reason':'PreviewSession placed every clone at x=1000 with unrestricted camera; open review preview overlapped recorder clone. Root and two independent actual visual observers confirmed duplicate ears/faces/hands. Dedicated Unity preview scenes added; all initial captures excluded conservatively. Prior round full-resolution tilt comparison is clean.','quarantined_ids':[r['candidate_id'] for r in parents],'replacement_ids':[r['candidate_id'] for r in children],'new_recordings':36,'total_recordings_after_replacement':72,'labels_unchanged':True,'preview_session_sha256':file_hash(ROOT/'Assets/Scripts/ActionLanguage/Editor/PreviewSession.cs')}
with (R/'reports/capture_quarantine.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
pilot={children[3]['candidate_id'],children[9]['candidate_id']}
for name,selected in [('fixpilot',[r for r in children if r['candidate_id'] in pilot]),('fixmain',[r for r in children if r['candidate_id'] not in pilot])]:
    with (R/f'{name}_queue.jsonl').open('x',encoding='utf-8') as f:
        for r in selected:f.write(json.dumps({k:r[k] for k in ('candidate_id','parent_candidate_id','raw_text','input_role')}|{'decision':'execute','plan_json':json.dumps(r['config'],ensure_ascii=False,separators=(',',':'))},ensure_ascii=False)+'\n')
print(json.dumps({'quarantined':36,'new_children':36,'pilot':sorted(pilot)}))
