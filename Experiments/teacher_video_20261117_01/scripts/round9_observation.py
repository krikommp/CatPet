"""Read-only audit of the round-9 corpus snapshot, never imports or trains a model."""
from pathlib import Path
import ast, collections, hashlib, json, random, subprocess
R=Path(__file__).resolve().parents[1]
rows=[json.loads(x) for x in (R/'input/round9_observed/llm_v02_corpus.jsonl').read_text(encoding='utf-8-sig').splitlines() if x.strip()]
old=[json.loads(x) for x in (R/'input/Dataset/ActionCards/llm_v02_corpus.jsonl').read_text(encoding='utf-8-sig').splitlines() if x.strip()]
old_hashes={hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest() for x in old}
new=[(i+1,x) for i,x in enumerate(rows) if hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest() not in old_hashes]
# Run the unchanged legacy split function alone; do not execute training imports/main.
tree=ast.parse((R/'input/original_python/train_action_config.py').read_text(encoding='utf-8-sig'))
fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='split_by_group')
scope={'defaultdict':collections.defaultdict,'random':random}
exec(compile(ast.Module(body=[fn],type_ignores=[]),'legacy_split_only','exec'),scope)
decs=['execute','none','unsupported','ambiguous']
samples=[{'text':x['raw_text'],'group_id':x['group_id'],'targets':{'decision':decs.index(x['config']['decision'])}} for x in rows]
splits=dict(zip(['train','val','test'],scope['split_by_group'](samples)))
overlaps={}
for a,b in [('train','val'),('train','test'),('val','test')]:
 overlap=sorted({x['text'] for x in splits[a]}&{x['text'] for x in splits[b]})
 overlaps[a+'_'+b]={'same_text_count':len(overlap),'texts':overlap}
cfg=R/'reports/round9_configs.jsonl'
cfg.write_text(''.join(json.dumps(x['config'],ensure_ascii=False)+'\n' for x in rows),encoding='utf-8')
compiled={}
for version in ('baseline','patched'):
 out=subprocess.run([str(R/f'scripts/compiler_{version}.exe'),str(cfg)],check=True,capture_output=True,text=True,encoding='utf-8').stdout
 result=[json.loads(x) for x in out.splitlines() if x.strip()]
 compiled[version]={'passed':sum(x['compile_ok'] for x in result),'errors':dict(collections.Counter(x['error'] for x in result if not x['compile_ok']))}
 (R/f'reports/round9_compile_{version}.jsonl').write_text(''.join(json.dumps({**r,'raw_text':x['raw_text']},ensure_ascii=False)+'\n' for r,x in zip(result,rows)),encoding='utf-8')
persona=R/'input/gemini-cyber-cat.md'
report={'scope':'Observed corpus snapshot, not proof of which bytes running Gemini process loaded',
 'rows':len(rows),'new_or_changed_vs_initial_snapshot':len(new),'hypothetical_legacy_split_counts':{k:len(v) for k,v in splits.items()},
 'legacy_split_overlaps':overlaps,'compiler_audit':compiled,'persona_sha256':hashlib.sha256(persona.read_bytes()).hexdigest(),
 'persona_hard_constraint_conflicts':[
  {'recommendation':'cheer amplitude 1.15-1.20','constraint':'8.5 * amplitude <= 10, hence amplitude <= 1.176470588','policy':'reject out-of-range, do not silently clamp'},
  {'recommendation':'bow+blink duration 1700-1950ms','constraint':'blink maximum 1800ms; bow may be longer independently','policy':'do not assign 1950ms to blink'},
  {'recommendation':'tilt twice described as left-right sway','constraint':'current tilt curve goes to +20 degrees and returns to 0 each cycle; repeat is same-side','policy':'do not call this alternating left-right motion'},
  {'recommendation':'wag tail mapped to smile+cheer','constraint':'no tail resource in bound catalog','policy':'unsupported for explicit tail instruction; an optional dialogue mood interpretation requires input_role and policy disclosure'}],
 'our_training_started':False,'shared_changes':False}
(R/'reports/round9_observation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='legacy_split_overlaps'},ensure_ascii=False,indent=2))
print(json.dumps({k:v['same_text_count'] for k,v in overlaps.items()}))
