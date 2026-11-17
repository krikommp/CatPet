import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[3]
experiment = Path(__file__).resolve().parents[1]
output = experiment / 'reviews'

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def text_digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()

def canonical(value):
    return text_digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False))

source = experiment / 'revised_candidates_capture.jsonl'
records = {r['candidate_id']: r for r in (json.loads(line) for line in source.read_text(encoding='utf-8').splitlines())}
judgments = read(output / 'visual_b_judgments.json')
assert len(judgments) == 12
prompt = experiment / 'prompts/review_v1.md'
context_id = 'codex-desktop:/root/round2_visual_b:teacher_round2_20261117_192708'
reviews = []
notes = ['# Independent visual review B: final isolated captures', '',
         'Reviewer context: ' + context_id,
         'Provider: OpenAI / Codex desktop. Exact backend model identifier is not exposed.',
         'The judgments below follow actual inspection of every manifest contact-sheet page, every trajectory_focus row, and the listed full-resolution frames. The previous contaminated captures were not used as visual evidence for these replacement judgments.',
         'Semantic scores are binary under the admission rubric. Rejected or uncertain clips receive no naturalness score. Parameter labels alone do not establish visual gesture semantics.', '']

for cid, judgment in judgments.items():
    row = records[cid]
    manifest_path = experiment / 'observations' / cid / 'observation_manifest.json'
    manifest = read(manifest_path)
    report = read(manifest['physical_integrity_report']['path'])
    evidence = read(manifest['evidence']['path'])
    done = read(manifest['done_report']['path'])
    assert report['valid'] and report['full_decode'] and manifest['every_frame_included']
    assert done['finished'] and done['failed'] == 0 and done['completed'] == done['total']
    assert manifest['candidate_id'] == cid
    assert manifest['raw_text'] == row['raw_text'] and manifest['input_role'] == row['input_role']
    assert manifest['config'] == row['config'] == json.loads(evidence['config_json'])
    assert report['config_sha256'] == manifest['config_sha256'] == canonical(row['config'])
    for key in ['candidate_id', 'parent_candidate_id', 'input_role']:
        assert evidence[key] == row[key]
    assert evidence['raw_text_sha256'] == text_digest(row['raw_text'])
    for key in ['compile_ok', 'playback_completed', 'encoder_closed', 'source_hashes_unchanged', 'asset_hashes_unchanged']:
        assert evidence[key] is True
    assert not evidence['capture_error']
    for artifact in report['artifacts']:
        assert digest(artifact['source_path']) == artifact['sha256'], artifact['source_path']
    bound_artifacts = manifest['contact_sheets'] + [manifest[k] for k in ['evidence', 'video', 'full_trajectory', 'metadata', 'done_report', 'queue', 'physical_integrity_report', 'trajectory_focus']]
    for artifact in bound_artifacts:
        assert digest(artifact['path']) == artifact['sha256'], artifact['path']
    focus = [json.loads(line) for line in Path(manifest['trajectory_focus']['path']).read_text(encoding='utf-8').splitlines()]
    assert len(focus) == manifest['trajectory_frame_count'] == manifest['focused_trajectory_frame_count'] == manifest['contact_sheet_frame_count']
    assert [r['frame_index'] for r in focus] == list(range(len(focus)))
    assert report['video_sha256'] == manifest['video']['sha256'] == evidence['video_sha256']
    assert report['evidence_sha256'] == manifest['evidence']['sha256']
    generation_source = row['provenance']['generation_source_file']
    assert digest(generation_source) == row['provenance']['generation_source_sha256']
    frames = [manifest_path.parent / 'frames' / f'frame_{i:06d}.png' for i in judgment['frames']]
    for frame in frames:
        assert frame.is_file()
    paths = [a['path'] for a in manifest['contact_sheets']] + [str(manifest_path), manifest['trajectory_focus']['path'], manifest['full_trajectory']['path']] + [str(p) for p in frames]
    accepted = 'naturalness' in judgment
    assert not accepted or judgment['naturalness'] >= 0.70
    reviewed_at = datetime.now(timezone.utc).isoformat()
    assert datetime.fromisoformat(reviewed_at) >= datetime.fromisoformat(evidence['completed_utc'].replace('Z', '+00:00'))
    review = {
        'reviewer_type': 'AI', 'provider': 'OpenAI / Codex desktop',
        'model': 'Codex (exact backend model identifier not exposed)',
        'context_id': context_id, 'prompt_version': 'codex-review-round2.v1',
        'prompt_sha256': digest(prompt), 'rubric_version': 'codex-independent-video.v1',
        'reviewed_at': reviewed_at, 'status': 'accepted' if accepted else 'rejected',
        'semantic_match': accepted, 'scores': {'semantic': 1 if accepted else 0},
        'candidate_id': cid, 'parent_candidate_id': row['parent_candidate_id'],
        'input_role': row['input_role'], 'raw_text_sha256': text_digest(row['raw_text']),
        'config_sha256': canonical(row['config']), **report['bindings'],
        'evidence_sha256': manifest['evidence']['sha256'], 'video_sha256': manifest['video']['sha256'],
        'rationale': judgment['notes'],
        'observation': {
            'method': 'timestamped_frames_and_trajectory', 'full_clip_observed': True,
            'limitations': [] if accepted else [judgment['limitation']],
            'artifact_paths': paths,
            'artifact_hashes': [{'path': p, 'sha256': digest(p)} for p in paths],
            'contact_sheet_pages_observed': len(manifest['contact_sheets']),
            'trajectory_rows_observed': len(focus),
            'additional_full_frames_observed': judgment['frames'],
        },
        'candidate_source_path': str(source), 'candidate_source_sha256': digest(source),
        'candidate_record_sha256': canonical(row),
        'generation_source_path': generation_source, 'generation_source_sha256': digest(generation_source),
        'evidence_path': manifest['evidence']['path'],
        'physical_integrity_report_path': manifest['physical_integrity_report']['path'],
        'physical_integrity_report_sha256': manifest['physical_integrity_report']['sha256'],
    }
    assert context_id != row['generation']['context_id']
    if accepted:
        review['scores']['naturalness'] = judgment['naturalness']
    else:
        review['training_eligible'] = False
    reviews.append(review)
    notes.extend([f'## {cid}', '', 'Raw instruction: ' + row['raw_text'],
                  'Input role: ' + row['input_role'] + '; parent: ' + row['parent_candidate_id'],
                  'Result: ' + review['status'] + '; semantic=' + str(review['scores']['semantic']) + ('; naturalness=' + str(judgment['naturalness']) if accepted else '; no naturalness score'),
                  'Observed: ' + str(len(manifest['contact_sheets'])) + ' complete contact-sheet pages, all ' + str(len(focus)) + ' focus rows, full frames ' + ', '.join(map(str, judgment['frames'])) + '.',
                  judgment['notes'], 'Review UTC: ' + reviewed_at, ''])

final_path = output / 'visual_b_reviews.jsonl'
final_path.write_text(''.join(json.dumps(r, ensure_ascii=False, allow_nan=False) + '\n' for r in reviews), encoding='utf-8')
(output / 'visual_b_notes.md').write_text('\n'.join(notes), encoding='utf-8')
print(json.dumps({'reviews': len(reviews), 'accepted': sum(r['status'] == 'accepted' for r in reviews),
                  'rejected': [r['candidate_id'] for r in reviews if r['status'] == 'rejected'],
                  'observed_pages': sum(r['observation']['contact_sheet_pages_observed'] for r in reviews),
                  'observed_focus_rows': sum(r['observation']['trajectory_rows_observed'] for r in reviews),
                  'additional_full_frames': sum(len(r['observation']['additional_full_frames_observed']) for r in reviews),
                  'output': str(final_path), 'sha256': digest(final_path)}, ensure_ascii=False, indent=2))
