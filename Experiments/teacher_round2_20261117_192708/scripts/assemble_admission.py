"""Assemble actual independent verdicts without generating any verdict or score."""
import argparse,collections,copy,datetime as dt,json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1];sys.path.insert(0,str(ROOT/'Tools/ActionEncoder'))
from review_evidence import file_hash,canonical_hash,text_hash
from input_constraints import validate_instruction_constraints
def jl(p):return [json.loads(x) for x in p.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',default='accepted_records.jsonl');args=ap.parse_args()
    candidates={r['candidate_id']:r for p in [R/'candidates.jsonl',*sorted(R.glob('revised_candidates*.jsonl'))] for r in jl(p)}
    evidence={};recordings=0;failures=[]
    for p in sorted(R.glob('*_done.json')):
        batch=json.loads(p.read_text(encoding='utf-8-sig'));assert batch['finished'],p
        recordings+=batch['total']
        for i in batch['items']:
            assert i['candidate_id'] not in evidence,'duplicate recording identity'
            if i['ok']:evidence[i['candidate_id']]=i['evidence_path']
            else:failures.append(i)
    assert recordings<=72
    reviews={};source={}
    for p in sorted((R/'reviews').glob('*reviews.jsonl')):
        for payload in jl(p):
            rev=payload.get('review',payload)
            assert rev['candidate_id']==payload['candidate_id'],'review wrapper identity mismatch'
            cid=rev['candidate_id'];assert cid not in reviews,f'duplicate review {cid}'
            assert cid in candidates,cid
            reviews[cid]=rev;source[cid]=p
    quarantined=set(json.loads((R/'reports/capture_quarantine.json').read_text(encoding='utf-8'))['quarantined_ids'])
    assert not quarantined.intersection(reviews),'Technical-quarantine parents cannot receive final admission reviews'
    pending=[cid for cid,r in candidates.items() if cid not in quarantined and cid not in reviews and (r['config']['decision']!='execute' or cid in evidence)]
    assert not pending,('missing actual reviews',pending)
    output=[]
    for cid,review in reviews.items():
        if review['status']!='accepted':continue
        r=copy.deepcopy(candidates[cid]);assert review['context_id']!=r['generation']['context_id']
        assert review['raw_text_sha256']==text_hash(r['raw_text']) and review['config_sha256']==canonical_hash(r['config'])
        assert review['semantic_match'] is True and review['scores']['semantic']==1
        audit=validate_instruction_constraints(r['raw_text'],r['config']);assert not audit['violations'] and not audit['unresolved'],cid
        r['source_type']='ai_video_reviewed' if r['config']['decision']=='execute' else 'ai_semantic_reviewed'
        if r['config']['decision']=='execute':
            assert cid in evidence;assert review['observation']['full_clip_observed'] is True
            assert review['scores']['naturalness']>=.70
            r['evidence_path']=evidence[cid]
        r['review']=review;r['training_eligible']=r['split']=='train';r['admission_status']='accepted_ai_review'
        r['provenance'].update(independent_review_file=str(source[cid].resolve()),independent_review_file_sha256=file_hash(source[cid]))
        output.append(r)
    new_output=list(output)
    prior_path=ROOT/'Experiments/teacher_round_20261117_184246/accepted_records.jsonl'
    prior=jl(prior_path)
    assert len(prior)==42 and all(r['split']=='train' for r in new_output)
    output=prior+new_output
    assert len({r['candidate_id'] for r in output})==len(output)
    assert [r for r in output if r['split']!='train']==[r for r in prior if r['split']!='train']
    bysplit={s:dict(collections.Counter(r['config']['decision'] for r in output if r['split']==s)) for s in ['train','val','test']}
    report={'created_at':dt.datetime.now(dt.timezone.utc).isoformat(),'generated_candidates_including_revisions':len(candidates),'recordings_attempted':recordings,'recording_failures':failures,'reviewed':len(reviews),'review_verdict_counts':dict(collections.Counter(r['status'] for r in reviews.values())),'accepted':len(output),'accepted_by_split':bysplit,'accepted_resource_coverage':dict(collections.Counter(a['resource_id'] for r in output for s in r['config']['steps'] for a in s['actions'])),'missing_reviews':pending,'accepted_ids':[r['candidate_id'] for r in output],'rejected_or_uncertain':[r for r in reviews.values() if r['status']!='accepted'],'release_approved':False}
    report.update(prior_records=42,new_accepted=len(new_output),prior_source_sha256=file_hash(prior_path),heldout_rows_unchanged=True,initial_guard_failures_preserved=['tr2-train-13','tr2-train-16','tr2-train-29','tr2-train-30'])
    with (R/args.output).open('x',encoding='utf-8') as f:
        for r in output:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    with (R/'reports'/('admission_'+Path(args.output).stem+'.json')).open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k not in ['accepted_ids','rejected_or_uncertain']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
