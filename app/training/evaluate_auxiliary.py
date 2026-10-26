"""Five-way auxiliary validation, explicitly separate from campus/final retrieval evaluation."""
import hashlib
import json
import sqlite3
from pathlib import Path
import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer
from train_text_models import explicit_groups, retrieval_loss

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT/'runtime/experiments/final-training-20261026/retriever-aux-v1'


def main():
    config = json.loads((RUN/'run.json').read_text(encoding='utf-8'))
    status = json.loads((RUN/'status.json').read_text(encoding='utf-8'))
    if status.get('state') != 'AUXILIARY_TRAINING_COMPLETE' or not status.get('reloadVerified'):
        raise ValueError('Training/reload not complete')
    db = sqlite3.connect(ROOT/'runtime/datasets/final-training-v1/auxiliary.sqlite')
    documents = dict(db.execute('SELECT id,text FROM documents'))
    groups = explicit_groups(list(db.execute("SELECT left_id,right_id,target FROM pairs WHERE split='aux_validation'")))
    db.close()
    outputs = {}
    torch.set_num_threads(4)
    for name,path in [('base',ROOT/'runtime/models/final/bge-base-zh-v1.5'/config['baseRevision']),('auxiliary_trained',RUN/status['checkpoint']/'model')]:
        model = AutoModel.from_pretrained(path,local_files_only=True,trust_remote_code=False).to('cuda').eval()
        tokenizer = AutoTokenizer.from_pretrained(path,local_files_only=True,trust_remote_code=False)
        predictions = []
        with torch.no_grad(),torch.autocast('cuda',dtype=torch.bfloat16):
            for group in groups:
                ids = [group['positiveId']]+group['negativeIds']
                tokens = tokenizer([documents[group['queryId']]]+[documents[key] for key in ids],padding=True,truncation=True,max_length=256,return_tensors='pt').to('cuda')
                embeddings = model(**tokens).last_hidden_state[:,0].float()
                q,p = embeddings[:1],embeddings[1:].unsqueeze(0)
                scores = (F.normalize(q,dim=-1)@F.normalize(p[0],dim=-1).T)[0]
                rank = 1+sum(float(score)>float(scores[0]) for score in scores[1:])
                predictions.append({'queryId':group['queryId'],'sourceIds':ids,'cosines':scores.cpu().tolist(),'correctSourceRank':rank,'loss':retrieval_loss(q,p).item()})
        outputs[name] = {'count':len(predictions),'meanLoss':sum(p['loss'] for p in predictions)/len(predictions),
                         'fiveCandidateAccuracyAt1':sum(p['correctSourceRank']==1 for p in predictions)/len(predictions),'predictions':predictions}
        del model;torch.cuda.empty_cache()
    result = {'task':'RETRIEVAL_RELEVANCE','scope':'Small event/story auxiliary five-candidate validation, not full-library recall or campus correctness.',
              'split':'aux_validation','models':outputs,'campusQualityAccepted':False,'finalProtocolExecuted':False}
    (RUN/'auxiliary-evaluation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({name:{k:v for k,v in output.items() if k!='predictions'} for name,output in outputs.items()}))


if __name__ == '__main__':
    main()
