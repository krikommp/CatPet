"""Read-only train/validation inference and feature diagnostics; no training."""
import collections,json,sys
from pathlib import Path
import torch
from transformers import BertModel
HERE=Path(__file__).resolve().parent;ROUND=HERE.parent;ROOT=ROUND.parents[1]
sys.path.insert(0,str(ROOT/'Tools/ActionEncoder'))
from encoder import LocalEncoder,DEFAULT_MODEL_DIR
from action_config_schema import DECISIONS,RESOURCE_IDS,format_input_text,decode_config
from train_action_config import pool_backbone,prediction_metrics
from training_data import build_samples
torch.set_num_threads(2)
rows=[json.loads(x) for x in (ROUND/'accepted_records.jsonl').read_text(encoding='utf-8').splitlines()]
rows=[r for r in rows if r['split'] in ('train','val')]
enc=LocalEncoder(config_head_dir=ROUND/'checkpoint_epoch20',threads=2)
samples=build_samples([json.loads(x) for x in (ROUND/'accepted_records.jsonl').read_text(encoding='utf-8').splitlines()],enc.tokenizer,128)
samples=[s for s in samples if s['split'] in ('train','val')]
texts=[format_input_text(r['raw_text'],r['input_role']) for r in rows]
inputs=enc.tokenizer(texts,padding=True,truncation=False,return_tensors='pt')
def stats(x):
    x=x.detach().float();norm=torch.nn.functional.normalize(x,dim=1);sim=norm@norm.T;off=sim[~torch.eye(len(x),dtype=torch.bool)]
    return {'mean_norm':float(x.norm(dim=1).mean()),'mean_feature_std':float(x.std(dim=0).mean()),'pairwise_cosine_min':float(off.min()),'pairwise_cosine_mean':float(off.mean()),'pairwise_cosine_max':float(off.max()),'centered_energy_fraction':float(((x-x.mean(0))**2).sum()/(x**2).sum())}
def probs(logits,labels):
    v=logits.softmax(-1);top=torch.topk(v,min(3,len(labels)))
    return {'argmax':labels[int(logits.argmax())],'top3':[(labels[int(i)],float(s)) for i,s in zip(top.indices,top.values)],'probabilities':[float(p) for p in v]}
with torch.inference_mode():
    base=pool_backbone(enc.model,inputs);trained=pool_backbone(enc.config_backbone,inputs)
    disc=enc.config_head.forward_discrete(trained);params=enc.config_head.forward_params(disc['h'],disc['resource_id'].argmax(-1))
    diagnostic=[]
    for i,row in enumerate(rows):
        item={k:row[k] for k in ['candidate_id','split','raw_text','input_role','config']}
        item.update(decision=probs(disc['decision'][i],DECISIONS),resources=[probs(disc['resource_id'][i,j],RESOURCE_IDS) for j in range(2)],stage_ids=disc['stage'][i].argmax(-1).tolist(),cycle_count_ids=disc['cycle_count'][i].argmax(-1).tolist())
        try:item['raw_decoded_config']=decode_config({k:v[i:i+1] for k,v in disc.items()},params[i:i+1])
        except Exception as e:item['decode_error']=str(e)
        diagnostic.append(item)
    metrics={}
    for split in ('train','val'):
        ix=[i for i,r in enumerate(rows) if r['split']==split]
        metrics[split],_=prediction_metrics(enc.config_head,trained[ix],[samples[i] for i in ix])
    # Same saved state through the trainer's default attention construction.
    bb=BertModel.from_pretrained(str(DEFAULT_MODEL_DIR),local_files_only=True,use_safetensors=True,add_pooling_layer=False)
    bb.load_state_dict(torch.load(ROUND/'checkpoint_epoch20/backbone_state.pt',map_location='cpu',weights_only=True));bb.eval()
    training_style=pool_backbone(bb,inputs)
    raw_single=pool_backbone(enc.config_backbone,enc.tokenizer([texts[0]],return_tensors='pt'))
    inferred=enc.config_head.forward_discrete(raw_single)
    parity={'trainer_attention':bb.config._attn_implementation,'runtime_attention':enc.config_backbone.config._attn_implementation,'pooled_max_abs_difference':float((trained-training_style).abs().max()),'single_vs_batched_first_feature_max_abs_difference':float((raw_single-trained[:1]).abs().max()),'single_vs_batched_first_decision_max_abs_difference':float((inferred['decision']-disc['decision'][:1]).abs().max())}
summary={'checkpoint_id':enc.config_head_manifest['checkpoint_id'],'inputs':'train_and_val_only; fixed test not rerun','count':len(rows),'features':{'base':stats(base),'trained':stats(trained),'head_hidden':stats(disc['h'])},'metrics':metrics,'decision_argmax':dict(collections.Counter(x['decision']['argmax'] for x in diagnostic)),'slot0_argmax':dict(collections.Counter(x['resources'][0]['argmax'] for x in diagnostic)),'slot1_argmax':dict(collections.Counter(x['resources'][1]['argmax'] for x in diagnostic)),'decision_probability_std':disc['decision'].softmax(-1).std(0).tolist(),'parity':parity,'mean_decision_probability':dict(zip(DECISIONS,disc['decision'].softmax(-1).mean(0).tolist()))}
with (HERE/'checkpoint_probe_rows.jsonl').open('x',encoding='utf-8') as f:
    for row in diagnostic:f.write(json.dumps(row,ensure_ascii=False)+'\n')
with (HERE/'checkpoint_probe_summary.json').open('x',encoding='utf-8') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
print(json.dumps(summary,ensure_ascii=False,indent=2))
