"""Preserve four unrecorded guard failures and author explicit-scope children."""
import json,sys,datetime as dt
from pathlib import Path
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1];sys.path.insert(0,str(ROOT/'Tools/ActionEncoder'))
from input_constraints import validate_instruction_constraints
from review_evidence import file_hash
rows=[json.loads(x) for x in (R/'candidates.jsonl').read_text(encoding='utf-8').splitlines()]
revisions={
 'tr2-train-13':'摇头两次，第一次600毫秒，第二次1100毫秒，逐次变慢。',
 'tr2-train-16':'示范侧抬右臂并张开手掌：挥手一次，持续900毫秒，随后放回。',
 'tr2-train-29':'做个俏皮练习：眨眼一次和歪头一次同时开始。',
 'tr2-train-30':'做眼睛与头部的配合练习，眨眼两次和摇头两次同时开始。'}
children=[];active=[]
for r in rows:
    if r['candidate_id'] in revisions:
        p=r['candidate_id'];r=json.loads(json.dumps(r));r.update(candidate_id=p+'-r1',parent_candidate_id=p,raw_text=revisions[p])
        r['generation'].update(generated_at=dt.datetime.now(dt.timezone.utc).isoformat(),revision_reason='Explicit scope wording after initial guard unresolved before any recording')
        r['provenance'].update(parent_candidate_id=p,parent_split='train',parent_semantic_family_id=r['semantic_family_id'],generation_source_file=str(Path(__file__).resolve()),generation_source_sha256=file_hash(__file__))
        children.append(r)
    audit=validate_instruction_constraints(r['raw_text'],r['config']);assert not audit['violations'] and not audit['unresolved'],(r['candidate_id'],audit)
    active.append(r)
with (R/'revised_candidates.jsonl').open('x',encoding='utf-8') as f:
    for r in children:f.write(json.dumps(r,ensure_ascii=False)+'\n')
for name,selected in [('pilot',active[:2]),('main',active[2:36])]:
    with (R/f'{name}_queue.jsonl').open('x',encoding='utf-8') as f:
        for r in selected:f.write(json.dumps({k:r[k] for k in ('candidate_id','parent_candidate_id','raw_text','input_role')}|{'decision':'execute','plan_json':json.dumps(r['config'],ensure_ascii=False,separators=(',',':'))},ensure_ascii=False)+'\n')
print('54 active candidates, 4 preserved original guard failures, 36 queued executions')
