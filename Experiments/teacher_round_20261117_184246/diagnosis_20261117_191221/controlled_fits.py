"""Predeclared in-memory diagnostics. No checkpoint save and no fixed-test access."""
import collections,datetime as dt,json,sys,time
from pathlib import Path
import torch
from transformers import BertModel,BertTokenizer
D=Path(__file__).resolve().parent;R=D.parent;ROOT=R.parents[1]
sys.path.insert(0,str(ROOT/'Tools/ActionEncoder'))
from encoder import DEFAULT_MODEL_DIR,verify_model
from action_config_schema import ActionConfigV02Model,canonicalize_config,format_input_text,decode_config,DECISIONS,RESOURCE_IDS
from train_action_config import compute_loss,make_batch_tensors,pool_backbone,prediction_metrics,structure
from review_evidence import file_hash
plan=json.loads((D/'controlled_fit_plan.json').read_text());torch.set_num_threads(plan['cpu_threads'])
ck=R/'checkpoint_epoch20'
protected={str(p):file_hash(p) for p in [ck/'config_head.pt',ck/'backbone_state.pt',ck/'manifest.json',R/'frozen_snapshot/manifest.json',ROOT/'Tools/ActionEncoder/checkpoints/v02_latest/config_head.pt']}
def read_samples(split):
    rows=[json.loads(s) for s in (ck/f'{split}_split.jsonl').read_text(encoding='utf-8').splitlines()]
    return [{**r,'text':r['raw_text'],'model_text':format_input_text(r['raw_text'],r['input_role']),'targets':canonicalize_config(r['config'])} for r in rows]
train,val=read_samples('train'),read_samples('val');assert len(train)==27 and len(val)==8
verify_model(DEFAULT_MODEL_DIR)
tokenizer=BertTokenizer.from_pretrained(str(DEFAULT_MODEL_DIR),local_files_only=True)
train_t,val_t=make_batch_tensors(train),make_batch_tensors(val)
inputs={s:tokenizer([x['model_text'] for x in rows],padding=True,truncation=False,return_tensors='pt') for s,rows in [('train',train),('val',val)]}
def observation(model,bb,rows,targets,split,cached=None):
    model.eval();bb.eval()
    with torch.inference_mode():
        features=cached if cached is not None else pool_backbone(bb,inputs[split])
        d=model.forward_discrete(features);params=model.forward_params(d['h'],d['resource_id'].argmax(-1))
        loss=float(compute_loss(model,features,targets));guards,_=prediction_metrics(model,features,rows)
        raw=collections.Counter();details=[]
        for i,r in enumerate(rows):
            dec=DECISIONS[int(d['decision'][i].argmax())];raw['decision_correct']+=int(dec==r['config']['decision']);raw['total']+=1
            raw['false_execute_before_guard']+=int(r['config']['decision']!='execute' and dec=='execute')
            if r['config']['decision']=='execute':
                raw['execute_total']+=1
                raw['resource_slots_correct']+=int(torch.equal(d['resource_id'][i].argmax(-1),targets['resource_id'][i]))
                active=targets['resource_id'][i]>0
                raw['active_cycle_counts_correct']+=int(torch.equal(d['cycle_count'][i].argmax(-1)[active],targets['cycle_count'][i][active]))
            try:
                cfg=decode_config({k:v[i:i+1] for k,v in d.items()},params[i:i+1]);correct=structure(cfg)==structure(r['config'])
                raw['structure_correct_before_numeric_guard']+=int(correct)
                raw['execute_structure_correct_before_numeric_guard']+=int(correct and r['config']['decision']=='execute')
                details.append({'candidate_id':r['candidate_id'],'gold':r['config'],'predicted':cfg})
            except Exception as e:
                raw['decoder_errors']+=1;details.append({'candidate_id':r['candidate_id'],'error':str(e)})
        return {'loss_eval':loss,'raw_component_metrics':dict(raw),'strict_guarded_metrics':guards,'decision_histogram':dict(collections.Counter(DECISIONS[int(i)] for i in d['decision'].argmax(-1))),'first_resource_histogram':dict(collections.Counter(RESOURCE_IDS[int(i)] for i in d['resource_id'][:,0].argmax(-1)))},details
results=[];started=time.time()
for arm in plan['arms']:
    torch.manual_seed(plan['seed'])
    bb=BertModel.from_pretrained(str(DEFAULT_MODEL_DIR),local_files_only=True,use_safetensors=True,add_pooling_layer=False)
    for p in bb.parameters():p.requires_grad=False
    layers=arm['unfreeze_last_layers']
    if layers:
        for layer in bb.encoder.layer[-layers:]:
            for p in layer.parameters():p.requires_grad=True
    model=ActionConfigV02Model(hidden_size=256)
    groups=[{'params':model.parameters(),'lr':arm['head_lr']}]
    if layers:groups.append({'params':[p for p in bb.parameters() if p.requires_grad],'lr':arm['backbone_lr']})
    optimizer=torch.optim.AdamW(groups,weight_decay=1e-2)
    cache={}
    if not layers:
        bb.eval()
        with torch.no_grad():cache={s:pool_backbone(bb,v).detach() for s,v in inputs.items()}
    for step in range(201):
        if step:
            model.train();bb.train(bool(layers));ix=torch.randperm(len(train)).tolist()
            target={k:v[ix] for k,v in train_t.items()}
            optimizer.zero_grad()
            if layers:
                batch=tokenizer([train[i]['model_text'] for i in ix],padding=True,truncation=False,return_tensors='pt');features=pool_backbone(bb,batch)
            else:features=cache['train'][ix]
            loss=compute_loss(model,features,target);loss.backward();optimizer.step()
        if step not in plan['observation_steps']:continue
        rec={'arm':arm['name'],'step':step,'elapsed_seconds':round(time.time()-started,2)}
        for split,rows,targets in [('train',train,train_t),('val',val,val_t)]:
            rec[split],details=observation(model,bb,rows,targets,split,cache.get(split))
            with (D/f"fit_{arm['name']}_{step}_{split}.jsonl").open('x',encoding='utf-8') as f:
                for p in details:f.write(json.dumps(p,ensure_ascii=False)+'\n')
        if arm['name']=='original_recipe_200_updates' and step==6:
            head_saved=torch.load(ck/'config_head.pt',map_location='cpu',weights_only=True);bb_saved=torch.load(ck/'backbone_state.pt',map_location='cpu',weights_only=True)
            rec['reproduction']={'head_max_abs_diff':max(float((v-head_saved[k]).abs().max()) for k,v in model.state_dict().items()),'backbone_max_abs_diff':max(float((v-bb_saved[k]).abs().max()) for k,v in bb.state_dict().items())}
        results.append(rec)
        with (D/'controlled_fit_metrics.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(rec,ensure_ascii=False)+'\n')
        print(json.dumps({'arm':arm['name'],'step':step,'train':rec['train']['raw_component_metrics'],'val':rec['val']['raw_component_metrics'],'reproduction':rec.get('reproduction')},ensure_ascii=False),flush=True)
assert all(file_hash(p)==h for p,h in protected.items())
summary={'completed_at':dt.datetime.now(dt.timezone.utc).isoformat(),'plan_sha256':file_hash(D/'controlled_fit_plan.json'),'source_sha256':file_hash(__file__),'elapsed_seconds':time.time()-started,'protected_files_unchanged':True,'saved_checkpoint':False,'fixed_test_accessed':False,'results':results}
with (D/'controlled_fit_summary.json').open('x',encoding='utf-8') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
print('Diagnostic complete; no checkpoint saved.',flush=True)
