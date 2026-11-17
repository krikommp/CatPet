"""Prepare reviewable diffs and hashes. Never applies anything to shared files."""
from pathlib import Path
import datetime,difflib,hashlib,json
R=Path(__file__).resolve().parents[1]
project=R.parents[1]
patches=R/'patches';patches.mkdir(exist_ok=True)
files=[]
for name in ['action_config_schema.py','encoder.py','train_action_config.py']:
    files.append((R/'input/original_python'/name,R/'source'/name,'Tools/ActionEncoder/'+name))
files.append((R/'input/Assets/Scripts/ActionLanguage/ActionConfigCompiler.cs',R/'source/csharp/ActionConfigCompiler.cs','Assets/Scripts/ActionLanguage/ActionConfigCompiler.cs'))
records=[]
for original,patched,target in files:
    before=hashlib.sha256(original.read_bytes()).hexdigest()
    after=hashlib.sha256(patched.read_bytes()).hexdigest()
    text=''.join(difflib.unified_diff(original.read_text(encoding='utf-8-sig').splitlines(True),patched.read_text(encoding='utf-8-sig').splitlines(True),fromfile='original/'+target,tofile='experiment/'+target))
    patch=patches/(patched.name+'.patch');patch.write_text(text,encoding='utf-8')
    live=project/target
    records.append({'shared_target':target,'baseline_sha256':before,'patched_sha256':after,
                    'shared_still_matches_baseline':live.exists() and hashlib.sha256(live.read_bytes()).hexdigest()==before,
                    'diff':str(patch.relative_to(R)),'applied_to_shared':False})
added=R/'source/input_constraints.py'
if added.is_file():
    target='Tools/ActionEncoder/input_constraints.py'
    patch=patches/'input_constraints.py.patch'
    patch.write_text(''.join(difflib.unified_diff([],added.read_text(encoding='utf-8-sig').splitlines(True),fromfile='/dev/null',tofile='experiment/'+target)),encoding='utf-8')
    records.append({'shared_target':target,'new_file':True,'baseline_sha256':None,
                    'patched_sha256':hashlib.sha256(added.read_bytes()).hexdigest(),
                    'shared_still_matches_baseline':not (project/target).exists(),
                    'diff':str(patch.relative_to(R)),'applied_to_shared':False})
artifacts=[]
for folder in ['source','scripts','reports','data','reviews']:
    for p in sorted((R/folder).rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix in {'.py','.cs','.ps1','.md','.json','.jsonl'}:
            artifacts.append({'path':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
manifest={'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'purpose':'Assist Gemini round 9; patches are isolated and NOT deployed',
          'new_training_started':False,'new_recording_started':False,'weights_replaced':False,'persona_file':'input/gemini-cyber-cat.md',
          'persona_sha256':hashlib.sha256((R/'input/gemini-cyber-cat.md').read_bytes()).hexdigest(),'patches':records,'artifacts':artifacts}
(R/'assistance_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'patches':len(records),'artifacts':len(artifacts),'shared_code_unchanged':all(x['shared_still_matches_baseline'] for x in records),'training_started':False},ensure_ascii=False))
