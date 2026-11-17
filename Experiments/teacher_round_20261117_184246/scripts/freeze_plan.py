"""Freeze scenarios before the teacher writes candidate utterances/configs."""
import datetime as dt, hashlib, json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
families={
'train':[
'single_blink_ack','single_nod_assent','single_shake_refusal','single_tilt_curiosity','single_look_search','single_smile_photo','single_angry_protest','single_shy_embarrassment','single_surprise_alarm','single_wave_greet','single_cheer_success','single_bow_respect',
'seq_blink_nod_wakeup','seq_angry_smile_reconcile','seq_look_wave_spot_friend','seq_bow_shy_apology','seq_surprise_shake_disbelief','seq_tilt_blink_puzzle',
'par_smile_cheer_reward','par_smile_wave_welcome','par_angry_shake_denial','par_bow_blink_fatigue','par_shy_nod_accept','par_surprise_cheer_reveal',
'none_negate_all','none_static_server','none_discuss_emotion','none_quote_instruction','unsupported_tail','unsupported_locomotion','unsupported_four_cycles','unsupported_conflicting_face','ambiguous_repeat_no_context','ambiguous_reaction_unspecified','ambiguous_deictic','ambiguous_choose_adorable'],
'val':['seq_bow_wave_departure','seq_shy_smile_recover','seq_look_surprise_discover','repeat_nod_accelerate','repeat_wave_crescendo','repeat_tilt_decelerate',
'none_instruction_emotion_report','unsupported_three_actions','ambiguous_incomplete_order'],
'test':['par_blink_wave_signal','par_tilt_smile_pose','par_bow_angry_grudging','seq_cheer_bow_curtain','seq_smile_look_investigate','seq_nod_shake_correction',
'none_negated_specific_actions','unsupported_alternating_body','ambiguous_relative_missing_action']}
rows=[]
for split, fs in families.items():
    for i,f in enumerate(fs,1):
        decision=next((d for d in ('none','unsupported','ambiguous') if f.startswith(d+'_')),'execute')
        rows.append(dict(candidate_id=f'tr1-{split}-{i:02d}',parent_candidate_id='',group_id=f'tr1-{f}',semantic_family_id=f'tr1-{f}',scenario=f,split=split,planned_decision=decision))
plan=dict(created_at=dt.datetime.now(dt.timezone.utc).isoformat(),round='teacher_round_20261117_184246',status='experimental',planned_total=54,max_recordings=72,max_revisions_per_candidate=2,teacher_context='/root Codex desktop training chat',candidates=rows,
limitations=['Small sample; scenario families prevent paraphrase/parent leakage, not statistical independence of action primitives.','All instruction role for this bounded round; dialogue deferred.','Only blink officially calibrated; all others remain Candidate.','No old corpus or test fixture may enter admission.'])
with (R/'scenario_plan.json').open('x',encoding='utf-8') as f: json.dump(plan,f,ensure_ascii=False,indent=2)
root=R.parents[1]
protected=[root/'Tools/ActionEncoder/checkpoints/v02_latest/config_head.pt',root/'Tools/ActionEncoder/checkpoints/v02_latest/backbone_state.pt',root/'Tools/ActionEncoder/checkpoints/v02_latest/manifest.json',root/'Dataset/ActionCards/llm_v02_corpus.jsonl']
with (R/'protected_before.json').open('x',encoding='utf-8') as f: json.dump({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected if p.is_file()},f,indent=2)
print(R.resolve())
