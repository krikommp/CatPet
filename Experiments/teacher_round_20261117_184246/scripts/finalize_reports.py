"""Summarize observed completed training/evaluations; never changes checkpoints."""
import collections,datetime as dt,hashlib,json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1];sys.path.insert(0,str(ROOT/'Tools/ActionEncoder'))
from retrain_and_eval import structure
from review_evidence import file_hash
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def jl(p):return [json.loads(x) for x in p.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
claim=read(R/'training_claim.json');assert claim['status']=='completed' and claim['exit_code']==0
ck=R/'checkpoint_epoch20';manifest=read(ck/'manifest.json');epochs=jl(ck/'epoch_metrics.jsonl')
assert [r['epoch'] for r in epochs]==list(range(1,21))
for e in epochs:
    p=ck/e['validation_predictions']['path'];assert file_hash(p)==e['validation_predictions']['sha256'];assert len(jl(p))==8
new=read(R/'reports/new_checkpoint_fixed_test.json');old=read(R/'reports/round9_same_fixed_test_diagnostic.json')
assert new['data']['snapshot_manifest_sha256']==old['data']['snapshot_manifest_sha256']==file_hash(R/'frozen_snapshot/manifest.json')
assert [(r['raw_text'],r['input_role']) for r in new['predictions']]==[(r['raw_text'],r['input_role']) for r in old['predictions']]
comparison=[];failures=[]
for label,report in [('teacher_round1',new),('round9_diagnostic',old)]:
    m=report['metrics'];comparison.append({'model':label,'checkpoint_id':report['checkpoint_id'],'total':m['total'],'decision_correct':m.get('decision_correct',0),'structure_correct':m.get('structure_correct',0),'execute_structure_correct':m.get('execute_structure_correct',0),'execute_total':m.get('gold_execute',0),'technical_errors':m.get('technical_errors',0),'false_execution':sum(m.get('false_execute_'+d,0) for d in ['none','unsupported','ambiguous']),'nonexecute_total':sum(m.get('gold_'+d,0) for d in ['none','unsupported','ambiguous'])})
    for p in report['predictions']:
        if p.get('technical_error') or structure(p['predicted'])!=structure(p['expected']):failures.append({'model':label,**p})
with (R/'reports/fixed_test_failures.jsonl').open('x',encoding='utf-8') as f:
    for p in failures:f.write(json.dumps(p,ensure_ascii=False)+'\n')
protected=read(R/'protected_before.json')
prior=read(ROOT/'Experiments/workflow_fix_20261117/reports/final_inventory.json')['protected_inputs']
for p in prior:protected[str(ROOT/p['path'])]=p['sha256']
protection=[{'path':p,'sha256':file_hash(p),'unchanged':file_hash(p)==sha} for p,sha in protected.items()]
assert all(x['unchanged'] for x in protection)
env=read(R/'reports/environment_before_training.json')
oldpath=Path(env['old_checkpoint']);oldunchanged=all(file_hash(oldpath/n)==h for n,h in env['old_checkpoint_hashes'].items());assert oldunchanged
accepted=jl(R/'accepted_records.jsonl');resources={s:sorted({a['resource_id'] for r in accepted if r['split']==s for step in r['config']['steps'] for a in step['actions']}) for s in ['train','val','test']}
report={'completed_at':dt.datetime.now(dt.timezone.utc).isoformat(),'training_completed':True,'epoch_count':len(epochs),'selected_epoch':manifest['best_epoch'],'checkpoint_id':manifest['checkpoint_id'],'checkpoint_dir':str(ck),'checkpoint_hashes':{n:file_hash(ck/n) for n in ['manifest.json','config_head.pt','backbone_state.pt']},'snapshot_manifest_sha256':file_hash(R/'frozen_snapshot/manifest.json'),'fixed_test_comparison':comparison,'protected_inputs':protection,'frozen_round9_copy_unchanged':oldunchanged,'resources_by_split':resources,'all_20_epoch_predictions_verified':True,'train_loss_first':epochs[0]['train_loss'],'train_loss_last':epochs[-1]['train_loss'],'new_prediction_structure_histogram':dict(collections.Counter(str(structure(p['predicted'])) for p in new['predictions'] if 'predicted' in p)),'release_approved':False,'service_changed':False,'limitations':['42 admitted rows, 27 train, 7 test: too small for general reliability claims.','Only instruction inputs; dialogue not sampled.','No admitted cheer or bow; wave has heldout examples but no train examples.','Wave judgments depend on broad whole-arm interpretation; reviewer-specific rationales preserved.','Explicit duration/amplitude progression heldout cases are in validation, not final test; precise numeric generalization is not established.','Same primitive resources across semantic scenario families are intentional, not proof of statistical independence.','Semantic independence from round9 historical training data is not established.','Model predictions were evaluated offline, not re-recorded for visual acceptance.','Zero technical errors does not establish semantic correctness; all seven new predictions collapse to single blink.']}
with (R/'reports/completion_summary.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
print(json.dumps({k:report[k] for k in ['training_completed','epoch_count','selected_epoch','checkpoint_id','fixed_test_comparison','frozen_round9_copy_unchanged']},ensure_ascii=False,indent=2))
