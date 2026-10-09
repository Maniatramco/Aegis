"""Offline CPU cross-encoder. Only the setup script downloads model assets."""
import hashlib
import math
import os
import threading
from functools import lru_cache
from pathlib import Path

MODEL_ID='cross-encoder/ms-marco-MiniLM-L6-v2'
REVISION='233902d25c440f23af6f7d6e94d2946bac0bee0a'
MODEL_SHA256='5d3e70fd0c9ff14b9b5169a51e957b7a9c74897afd0a35ce4bd318150c1d4d4a'
TOKENIZER_BLOB='688882a79f44442ddc1f60d70334a7ff5df0fb47'
_load_lock=threading.Lock()
_loaded_paths=set()

class RerankerError(RuntimeError):pass

def enabled():
    value=os.getenv('AEGIS_RERANKER','none').lower()
    if value not in ('none','local'):raise RerankerError('AEGIS_RERANKER must be none or local.')
    return value=='local'

def candidate_limit(top_k):
    try:limit=int(os.getenv('AEGIS_RERANK_CANDIDATES','25'))
    except ValueError:raise RerankerError('Reranker candidate limit must be an integer from 1 to 100.')
    if not 1<=limit<=100:raise RerankerError('Reranker candidate limit must be an integer from 1 to 100.')
    return max(top_k,limit)

def model_directory():
    path=os.getenv('AEGIS_RERANK_MODEL_DIR')
    if not path:raise RerankerError('Set AEGIS_RERANK_MODEL_DIR to the downloaded local reranker directory.')
    return Path(path).resolve()

def verify_assets(directory):
    directory=Path(directory)
    try:
        digest=hashlib.sha256()
        with (directory/'onnx/model.onnx').open('rb') as source:
            for block in iter(lambda:source.read(1024*1024),b''):digest.update(block)
        data=(directory/'tokenizer.json').read_bytes()
    except OSError as exc:
        raise RerankerError('Local reranker files are missing. Run scripts/setup-reranker.py before enabling reranking.') from exc
    blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    if digest.hexdigest()!=MODEL_SHA256 or blob!=TOKENIZER_BLOB:
        raise RerankerError('Local reranker files failed integrity validation. Download the pinned model again.')

@lru_cache(maxsize=1)
def _load(directory):
    verify_assets(directory)
    try:
        import onnxruntime as ort
        from tokenizers import Tokenizer
        tokenizer=Tokenizer.from_file(str(Path(directory)/'tokenizer.json'))
        tokenizer.enable_truncation(max_length=512,strategy='only_second')
        tokenizer.enable_padding(pad_id=0,pad_token='[PAD]')
        question_tokenizer=Tokenizer.from_file(str(Path(directory)/'tokenizer.json'))
        question_tokenizer.enable_truncation(max_length=128)
        options=ort.SessionOptions()
        options.intra_op_num_threads=min(4,os.cpu_count() or 1)
        options.inter_op_num_threads=1
        session=ort.InferenceSession(str(Path(directory)/'onnx/model.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
    except Exception as exc:
        raise RerankerError('Local reranker could not load. Install backend/requirements-reranker.txt and check the model files.') from exc
    _loaded_paths.add(directory)
    return tokenizer,session,question_tokenizer

def load():
    # lru_cache alone can initialize the same model twice on concurrent first use.
    with _load_lock:return _load(str(model_directory()))

def status():
    active=enabled()
    return {'enabled':active,'provider':'local' if active else 'none',
            'model':MODEL_ID if active else None,'revision':REVISION if active else None,
            'candidate_limit':candidate_limit(1) if active else None,
            'ready':str(model_directory()) in _loaded_paths if active else False}

def predict(query,passages):
    tokenizer,session,question_tokenizer=load()
    # Preserve room for evidence even when the user's question is very long.
    question=question_tokenizer.decode(question_tokenizer.encode(query,add_special_tokens=False).ids,skip_special_tokens=True)
    scores=[]
    try:
        import numpy as np
        inputs={value.name for value in session.get_inputs()}
        for offset in range(0,len(passages),8):
            encodings=tokenizer.encode_batch([(question,p) for p in passages[offset:offset+8]])
            tensors={
                'input_ids':np.asarray([e.ids for e in encodings],dtype=np.int64),
                'attention_mask':np.asarray([e.attention_mask for e in encodings],dtype=np.int64),
                'token_type_ids':np.asarray([e.type_ids for e in encodings],dtype=np.int64)}
            logits=session.run(None,{name:tensors[name] for name in inputs})[0]
            if logits.shape!=(len(encodings),1):raise ValueError('Unexpected cross-encoder output shape')
            scores.extend(float(row[0]) for row in logits)
    except Exception as exc:raise RerankerError('Local reranker could not score the retrieved passages.') from exc
    return scores

def rank(query,candidates,top_k):
    if not candidates:return []
    try:
        scores=predict(query,[item['text'] for item in candidates])
        if len(scores)!=len(candidates) or any(not math.isfinite(score) for score in scores):
            raise ValueError('Invalid reranker scores')
    except RerankerError:raise
    except Exception as exc:raise RerankerError('Local reranker returned invalid scores.') from exc
    scored=[dict(item,rerank_score=score,retrieval_rank=index+1,rerank_model=MODEL_ID,rerank_revision=REVISION)
            for index,(item,score) in enumerate(zip(candidates,scores))]
    # Python's stable sort preserves retrieval order when model scores tie.
    return sorted(scored,key=lambda item:item['rerank_score'],reverse=True)[:top_k]
