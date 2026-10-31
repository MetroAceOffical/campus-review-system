"""Measurements for Web training; no optimizer or random-state changes."""
import time
import psutil
import hashlib,json

def initialization_identity(model,vocab,tokenizer=None):
    weights=hashlib.sha256()
    for key,tensor in model.state_dict().items():
        value=tensor.detach().contiguous().cpu()
        weights.update(key.encode());weights.update(str(value.dtype).encode());weights.update(str(tuple(value.shape)).encode());weights.update(value.numpy().tobytes())
    encoder={'vocab':tokenizer.get_vocab(),'specialTokens':tokenizer.special_tokens_map} if tokenizer is not None else {'vocab':vocab}
    return {'weightsSha256':weights.hexdigest(),'encoderSha256':hashlib.sha256(json.dumps(encoder,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()}

class Telemetry:
    def __init__(self,device):
        self.device=device;self.started=time.perf_counter();self.process=psutil.Process();self.process.cpu_percent()
    def sample(self,samples,seconds,gradient=None):
        value={'elapsedSeconds':time.perf_counter()-self.started,'batchSeconds':seconds,
               'samplesPerSecond':samples/seconds if seconds>0 else None,'hostRssBytes':self.process.memory_info().rss,
               'cpuPercent':self.process.cpu_percent()/max(1,psutil.cpu_count() or 1)}
        if gradient is not None:value['gradientNorm']=float(gradient)
        if str(self.device).startswith('cuda'):
            import torch
            value.update(cudaAllocatedBytes=torch.cuda.memory_allocated(self.device),cudaReservedBytes=torch.cuda.memory_reserved(self.device))
        return value

def evaluate_split(model,rows,forward,batch_size):
    import torch
    from torch.nn.functional import cross_entropy
    was_training=model.training;model.eval();loss=0.;correct=0;scores=[]
    try:
        with torch.no_grad():
            for begin in range(0,len(rows),batch_size):
                end=min(len(rows),begin+batch_size);logits=forward(begin,end).float()
                labels=torch.tensor([int(r['label']) for r in rows[begin:end]],device=logits.device)
                loss+=float(cross_entropy(logits,labels,reduction='sum').item())
                correct+=int((logits.argmax(-1)==labels).sum().item())
                scores.extend(logits.softmax(-1)[:,1].cpu().tolist())
    finally:model.train(was_training)
    return {'loss':loss/len(rows),'accuracy':correct/len(rows),'scores':scores}
