"""Reproducible isolated C# compilation checks against baseline and corrected compiler."""
from pathlib import Path
import collections
import hashlib
import json
import subprocess

RUN = Path(__file__).resolve().parents[1]
rows = [json.loads(line) for line in (RUN / 'input/Dataset/ActionCards/llm_v02_corpus.jsonl').read_text(encoding='utf-8-sig').splitlines() if line.strip()]
config_file = RUN / 'reports/compiler_configs.jsonl'
config_file.write_text(''.join(json.dumps(row['config'], ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')
summary = {}
for version in ('baseline', 'patched'):
    result = subprocess.run([str(RUN / f'scripts/compiler_{version}.exe'), str(config_file)], capture_output=True, text=True, encoding='utf-8', check=True)
    report = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert len(report) == len(rows)
    for item, original in zip(report, rows):
        item['raw_text'] = original['raw_text']
        item['group_id'] = original.get('group_id')
    (RUN / f'reports/compiler_{version}_corpus.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False) + '\n' for x in report),encoding='utf-8')
    summary[version] = {'rows':len(report),'compiled':sum(x['compile_ok'] for x in report),'errors':dict(collections.Counter(x['error'] for x in report if not x['compile_ok']))}
summary['execution_environment'] = 'Standalone Mono C# 9; actual project parser/resource catalog/native validator sources; no Unity scene/playback test'
summary['input_sha256'] = hashlib.sha256(config_file.read_bytes()).hexdigest()
(RUN / 'reports/compiler_audit_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
