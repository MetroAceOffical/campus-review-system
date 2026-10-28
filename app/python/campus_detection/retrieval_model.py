"""Explicit, hash-bound BGE encoder loading; no training or profile switching."""
import contextlib
from pathlib import Path

import numpy as np
from campus_detection.retrieval import _digest,_sha


def verified_identity(folder,expected_hashes,*,device='cuda',precision='BF16',batch_size=8):
    """Verify the checkpoint and describe it without loading a model."""
    if device not in {'cuda','cpu'} or precision not in {'FP32','BF16'} or device=='cpu' and precision!='FP32':raise ValueError('Unsupported retrieval execution policy')
    if not isinstance(batch_size,int) or isinstance(batch_size,bool) or not 1<=batch_size<=32:raise ValueError('Invalid encoding batch budget')
    folder=Path(folder)
    weights=set(expected_hashes)&{'model.safetensors','pytorch_model.bin'}
    if len(weights)!=1:raise ValueError('Bind exactly one verified encoder weight file')
    weight=next(iter(weights))
    required={'config.json',weight,'tokenizer.json','tokenizer_config.json','special_tokens_map.json'}
    optional={'vocab.txt','added_tokens.json'}
    present=required|{name for name in optional if (folder/name).exists()}
    if set(expected_hashes)!=present:raise ValueError('Bind all model and tokenizer components from a verified checkpoint manifest')
    for name,expected in expected_hashes.items():
        if not (folder/name).is_file() or _sha(folder/name)!=expected:raise ValueError('Retrieval model/tokenizer changed: '+name)
    tokenizer_hashes={name:expected_hashes[name] for name in sorted(present-{weight,'config.json'})}
    return {'weightSha256':expected_hashes[weight],'modelConfigSha256':expected_hashes['config.json'],
              'tokenizerSha256':_digest(tokenizer_hashes),'pooling':'CLS','normalization':'L2','precision':precision,
              'parameterPrecision':'FP32','device':device,'maxTokens':512,'batchSize':batch_size,
              'queryPrefix':'','documentPrefix':'','algorithmSha256':_sha(Path(__file__))}


def load_retrieval_model(folder,*,expected_hashes,device='cuda',precision='BF16',batch_size=8):
    import torch
    import torch.nn.functional as functional
    from transformers import AutoModel,AutoTokenizer
    identity=verified_identity(folder,expected_hashes,device=device,precision=precision,batch_size=batch_size)
    if device=='cuda' and (not torch.cuda.is_available() or precision=='BF16' and not torch.cuda.is_bf16_supported()):raise RuntimeError('Requested CUDA retrieval policy unavailable; do not change environments silently')
    folder=Path(folder);weight=next(iter(set(expected_hashes)&{'model.safetensors','pytorch_model.bin'}))
    tokenizer=AutoTokenizer.from_pretrained(folder,local_files_only=True,trust_remote_code=False,use_fast=True)
    model=AutoModel.from_pretrained(folder,local_files_only=True,trust_remote_code=False,use_safetensors=weight=='model.safetensors',weights_only=True).float().to(device).eval()
    if model.config.hidden_size!=768 or model.config.model_type!='bert':raise ValueError('Require the fixed 768-dimensional BGE BERT encoder')
    def encode(texts):
        if isinstance(texts,str) or any(not isinstance(text,str) or not text.strip() for text in texts):raise ValueError('Require a sequence of nonempty original text windows')
        if not len(texts):return np.empty((0,768),dtype=np.float32)
        output=[]
        for start in range(0,len(texts),batch_size):
            tokens=tokenizer(texts[start:start+batch_size],padding=True,truncation=False,return_tensors='pt',verbose=False)
            if tokens['input_ids'].shape[1]>512:raise ValueError('Retrieval window exceeds full512 budget; split without truncation')
            tokens={key:value.to(device) for key,value in tokens.items()}
            with torch.inference_mode(),torch.autocast('cuda',dtype=torch.bfloat16) if precision=='BF16' else contextlib.nullcontext():
                embeddings=model(**tokens).last_hidden_state[:,0].float()
            vectors=functional.normalize(embeddings,dim=-1).cpu().numpy()
            if not np.isfinite(vectors).all() or not np.allclose(np.linalg.norm(vectors,axis=1),1.,atol=1e-4):raise ValueError('Encoder returned invalid normalized vectors')
            output.append(vectors)
        return np.concatenate(output,axis=0)
    return {'model':model,'tokenizer':tokenizer,'identity':identity,'encode':encode}
