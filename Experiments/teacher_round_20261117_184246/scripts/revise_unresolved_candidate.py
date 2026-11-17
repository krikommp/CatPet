import copy,datetime as dt,json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R.parents[1]/'Tools/ActionEncoder'))
from input_constraints import validate_instruction_constraints
from review_evidence import file_hash
rows=[json.loads(x) for x in (R/'candidates.jsonl').read_text(encoding='utf-8').splitlines()]
old=next(r for r in rows if r['candidate_id']=='tr1-val-05')
new=copy.deepcopy(old);new['candidate_id']='tr1-val-05-r1';new['parent_candidate_id']=old['candidate_id']
new['raw_text']='挥手三次，每次900毫秒，幅度越来越大。'
new['provenance'].update(parent_split=old['split'],parent_semantic_family_id=old['semantic_family_id'],revision_reason='Original wording had unresolved unsupported_cycle_request in strict guard; same intended increasing amplitude, clearer literal wording.',generation_source_file=str(Path(__file__).resolve()),generation_source_sha256=file_hash(__file__))
new['generation']['generated_at']=dt.datetime.now(dt.timezone.utc).isoformat()
audit=validate_instruction_constraints(new['raw_text'],new['config']);assert not audit['violations'] and not audit['unresolved'],audit
with (R/'revised_candidates.jsonl').open('x',encoding='utf-8') as f:f.write(json.dumps(new,ensure_ascii=False)+'\n')
with (R/'reports/pre_recording_rejections.jsonl').open('x',encoding='utf-8') as f:f.write(json.dumps({'candidate_id':old['candidate_id'],'status':'technical_rejection','stage':'before_recording','reason':'strict instruction guard unresolved amplitude scope','replacement':new['candidate_id'],'recording_count':0},ensure_ascii=False)+'\n')
selected=[r for r in rows[2:] if r['config']['decision']=='execute' and r['candidate_id']!=old['candidate_id']]+[new]
with (R/'main_queue_v2.jsonl').open('x',encoding='utf-8') as f:
    for r in selected:f.write(json.dumps({k:r[k] for k in ('candidate_id','parent_candidate_id','raw_text','input_role')}|{'decision':'execute','plan_json':json.dumps(r['config'],ensure_ascii=False,separators=(',',':'))},ensure_ascii=False)+'\n')
print(json.dumps({'candidate_id':new['candidate_id'],'audit':audit},ensure_ascii=False))
