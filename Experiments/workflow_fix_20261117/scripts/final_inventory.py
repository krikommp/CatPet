"""Record changed sources and verify protected round-9 inputs were preserved."""
from pathlib import Path
import datetime, hashlib, json

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / 'Experiments/workflow_fix_20261117'
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

before = json.loads((RUN / 'before_manifest.json').read_text(encoding='utf-8-sig'))
changes = []
for row in before['files']:
    path = ROOT / row['path']
    after = sha(path) if path.is_file() else None
    if after != row['sha256']:
        changes.append({'path': row['path'], 'before_sha256': row['sha256'], 'after_sha256': after})
new_files = [
    'Tools/ActionEncoder/input_constraints.py', 'Tools/ActionEncoder/training_data.py',
    'Tools/ActionEncoder/review_evidence.py', 'Tools/ActionEncoder/test_training_workflow.py',
    'Tools/ActionEncoder/training_workflow.md', 'tests/test_review_evidence.py',
    'Assets/Scripts/ActionLanguage/Editor/PreviewRecordingEvidence.cs',
    'Assets/Scripts/ActionLanguage/Editor/ActionWorkflowVerifier.cs',
]
known = {str(Path(row['path'])).replace('\\','/') for row in before['files']}
for rel in new_files:
    if rel not in known:
        changes.append({'path': rel, 'before_sha256': None, 'after_sha256': sha(ROOT / rel)})
checkpoint = json.loads((ROOT / 'Experiments/teacher_video_20261117_01/reports/round9_checkpoint_snapshot.json').read_text(encoding='utf-8'))
preserved = []
for row in checkpoint['files']:
    path = ROOT / 'Tools/ActionEncoder/checkpoints/v02_latest' / row['file']
    preserved.append({'path': str(path.relative_to(ROOT)), 'sha256': sha(path), 'unchanged': sha(path) == row['sha256']})
for row in before['files']:
    if row['path'].replace('\\','/') == 'Dataset/ActionCards/llm_v02_corpus.jsonl':
        path = ROOT / row['path']
        preserved.append({'path': row['path'], 'sha256': sha(path), 'unchanged': sha(path) == row['sha256']})
report = {'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'shared_changes': changes, 'protected_inputs': preserved,
          'all_protected_inputs_unchanged': all(row['unchanged'] for row in preserved),
          'training_started': False, 'online_service_restarted': False,
          'real_ai_accepted_samples_created': 0}
(RUN / 'reports/final_inventory.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'shared_changed_or_new_files': len(changes), 'protected_inputs': len(preserved),
                  'all_protected_inputs_unchanged': report['all_protected_inputs_unchanged']}, ensure_ascii=False))
