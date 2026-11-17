"""Read-only target/grammar preflight. No model inference, optimizer or test rows."""
import datetime as dt,json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1];sys.path.insert(0,str(ROOT/'Tools/ActionEncoder'))
from feasible_config import make_feasible_batch
from literal_bindings import extract_exact_duration_bindings
from action_config_schema import ModelOutputError
from input_constraints import DURATION
from review_evidence import file_hash
def jl(p):return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
old=[r for r in jl(ROOT/'Experiments/teacher_round_20261117_184246/accepted_records.jsonl') if r['split']=='train']
new=jl(R/'revised_candidates_capture.jsonl')+[r for r in jl(R/'candidates.jsonl') if r['config']['decision']!='execute']
rows=old+new;assert len(rows)==81 and all(r['split']=='train' for r in rows)
batch=make_feasible_batch(rows)
audits=[]
for r in rows:
    if r['config']['decision']!='execute' or not DURATION.search(r['raw_text']):continue
    result={'candidate_id':r['candidate_id'],'raw_text':r['raw_text'],'source':'prior_train' if r in old else 'current_authored_train_pending_admission'}
    try:
        bindings,audit=extract_exact_duration_bindings(r['raw_text'],r['config'],r['input_role'])
        result.update(supported=True,binding_count=len(bindings),audit=audit)
    except ModelOutputError as e:result.update(supported=False,error=str(e),audit=e.binding_audit)
    audits.append(result)
report={'created_at':dt.datetime.now(dt.timezone.utc).isoformat(),'scope':'train only; authored pending visual admission included for representability preflight, no new admission inferred','model_loaded':False,'optimizer_started':False,'test_rows_accessed':False,'target_count':len(rows),'all_gold_parameters_representable':True,'target_tensor_shapes':{k:list(v.shape) for k,v in batch.items()},'literal_binding_source_sha256':file_hash(ROOT/'Tools/ActionEncoder/literal_bindings.py'),'duration_rows':len(audits),'supported_duration_rows':sum(x['supported'] for x in audits),'audits':audits}
with (R/'reports/authored_train_representation.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
print(json.dumps({k:report[k] for k in ['target_count','all_gold_parameters_representable','duration_rows','supported_duration_rows']}))
