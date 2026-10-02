"""Durable lease worker. Provider calls happen outside database transactions."""
import time, os, uuid, io, traceback, threading, zipfile
from sqlalchemy import select, update, or_, and_
from .core import Session, Record, Job, store, settings, uid, init, document_lock, execution_context
from . import core, dataset_models as routing
from . import providers

MAX_ATTEMPTS=3
_last_reconcile=0.0

def claim(job_id=None):
    now=time.time();token=uid()
    with Session.begin() as s:
        for expired in s.scalars(select(Job).where(Job.status=='running',Job.lease_until<now,Job.attempts>=MAX_ATTEMPTS)):
            expired.status='failed';expired.error='Worker recovery attempts exhausted';expired.lease_until=0
            target=s.get(Record,expired.target_id)
            if target:target.status='failed';target.error=expired.error
        candidate=s.scalar(select(Job).where(or_(Job.status=='queued',and_(Job.status=='running',Job.lease_until<now)),Job.attempts<MAX_ATTEMPTS,Job.id==job_id if job_id else True).order_by(Job.created_at).limit(1).with_for_update(skip_locked=True))
        if not candidate:return None
        result=s.execute(update(Job).where(Job.id==candidate.id,or_(Job.status=='queued',and_(Job.status=='running',Job.lease_until<now))).values(status='running',attempts=Job.attempts+1,lease_until=now+900,lease_token=token,updated_at=now))
        if result.rowcount!=1:return None
        return candidate.id,token

def checkpoint(jid,token,progress):
    with Session.begin() as s:
        j=s.get(Job,jid)
        if not j or j.status!='running' or j.lease_token!=token:raise InterruptedError('Job cancelled or lease lost')
        r=s.get(Record,j.target_id)
        if not r or r.status=='deleting':raise InterruptedError('Target deleted')
        j.progress=progress;j.lease_until=time.time()+900;j.updated_at=time.time()

def parse_document(name,raw):
    ext=name.rsplit('.',1)[-1].lower()
    if ext=='txt':return [{'page':1,'text':raw.decode('utf-8-sig')}]
    if ext=='pdf':
        from pypdf import PdfReader
        reader=PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:raise ValueError('Encrypted PDFs are unsupported. Upload an unlocked copy.')
        if len(reader.pages)>1000:raise ValueError('PDF exceeds 1000 page limit')
        pages=[];total=0
        for i,p in enumerate(reader.pages):
            text=p.extract_text() or '';total+=len(text)
            if total>5000000:raise ValueError('Document exceeds 5 million character text limit')
            pages.append({'page':i+1,'text':text})
        if sum(len(p['text'].strip()) for p in pages)<20:raise ValueError('No extractable text. Scanned PDFs require OCR, which is not supported in this release.')
        return pages
    if ext=='docx':
        from docx import Document
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries=archive.infolist();names=[e.filename for e in entries]
            if len(names)!=len(set(names)) or any(n.startswith('/') or '..' in n.replace('\\','/').split('/') for n in names):raise ValueError('Unsafe DOCX archive entries')
            if sum(e.file_size for e in entries)>100*1024*1024 or any(e.file_size>25*1024*1024 for e in entries):raise ValueError('DOCX decompressed content exceeds safety limits')
        doc=Document(io.BytesIO(raw));lines=[p.text for p in doc.paragraphs]
        lines += [' | '.join(c.text for c in row.cells) for t in doc.tables for row in t.rows]
        text='\n'.join(lines)
        if len(text)>5000000:raise ValueError('Document exceeds 5 million character text limit')
        return [{'page':None,'text':text}]
    raise ValueError('Unsupported document format')

def chunk_pages(did,pages,size,overlap):
    chunks=[]
    for page in pages:
        text=page['text']
        if len(chunks)+len(text)//(size-overlap)>5000:raise ValueError('Document exceeds 5000 chunk limit')
        for start in range(0,len(text),size-overlap):
            content=text[start:start+size]
            if not content.strip():continue
            ident=str(uuid.uuid5(uuid.NAMESPACE_URL,f'{did}:{page["page"]}:{start}:{providers.fingerprint()}:{content}'))
            chunks.append({'id':ident,'document_id':did,'page':page['page'],'offset':start,'text':content})
    if settings()['embedding_provider']=='sentence_transformers' and settings()['search_provider']!='oci':
        model=providers.local_model('sentence-transformers/all-MiniLM-L6-v2');tokenizer=model.tokenizer;limit=model.max_seq_length-2;safe=[]
        for chunk in chunks:
            offsets=tokenizer(chunk['text'],add_special_tokens=False,return_offsets_mapping=True)['offset_mapping']
            for n in range(0,max(1,len(offsets)),limit):
                part=chunk.copy()
                if offsets:
                    begin=offsets[n][0];end=offsets[min(n+limit,len(offsets))-1][1];part['text']=chunk['text'][begin:end];part['offset']+=begin
                part['id']=str(uuid.uuid5(uuid.NAMESPACE_URL,chunk['id']+':'+str(n)));safe.append(part)
        chunks=safe
    elif settings()['embedding_provider']=='openai' and settings()['search_provider']!='oci':
        safe=[]
        for chunk in chunks:
            for offset,text in providers.split_utf8_bounded(chunk['text']):
                part=chunk.copy();part['text']=text;part['offset']+=offset
                part['id']=str(uuid.uuid5(uuid.NAMESPACE_URL,chunk['id']+':utf8:'+str(offset)));safe.append(part)
        chunks=safe
    return chunks

def process(jid,token):
    payload=store.json('jobs/'+jid+'.json');snapshot=payload.get('execution')
    if not snapshot:raise ValueError('Legacy job has no model snapshot. Configure its dataset and submit a new indexing or extraction job.')
    with execution_context(snapshot):
        with Session() as session:job=session.get(Job,jid)
        if job.kind=='index':
            with document_lock('dataset-'+snapshot['dataset_id']):
                dataset=routing.owned(snapshot['dataset_id'],job.owner,'knowledge_base')
                if routing.dataset_config(dataset).get('index_generation')!=snapshot['index_generation']:raise ValueError('Dataset embedding configuration changed. Submit a new reindex job.')
                _process(jid,token,snapshot)
        else:_process(jid,token,snapshot)

def _process(jid,token,snapshot):
    with Session() as s:
        j=s.get(Job,jid);record=s.get(Record,j.target_id)
        if not record:raise ValueError('Target no longer exists')
        kind=j.kind;did=record.id;name=record.name;owner=record.owner;kb=record.parent_id;ref=record.ref
    cfg=settings();checkpoint(jid,token,10)
    if kind=='index' and kb!=snapshot['dataset_id']:raise ValueError('Document dataset changed; submit a new indexing job.')
    if kind=='index':
        consent=store.json('jobs/'+jid+'.json').get('allow_external',False)
        if (cfg['embedding_provider']=='openai' or cfg['search_provider']=='oci') and not consent:raise ValueError('External embedding/indexing requires explicit external data transmission consent')
        with Session.begin() as s:s.get(Record,did).status='processing'
        pages=parse_document(name,store.get(ref));chunks=chunk_pages(did,pages,cfg['chunk_size'],cfg['chunk_overlap'])
        if not chunks:raise ValueError('Document has no usable text')
        if len(chunks)>5000:raise ValueError('Document exceeds 5000 chunk processing limit')
        store.put_json('documents/'+did+'/parsed.json',{'pages':pages})
        store.put_json('documents/'+did+'/chunks.json',{'chunks':chunks,'fingerprint':providers.fingerprint(),'chunk_size':cfg['chunk_size'],'chunk_overlap':cfg['chunk_overlap']})
        checkpoint(jid,token,35)
        vectors=[]
        if cfg['search_provider']=='oci':
            providers.delete_vectors(did)
            # Cleanup and crash recovery from this point belong to the NEW destination.
            store.put_json('documents/'+did+'/index-execution.json',snapshot)
            providers.oci_vector().upload_document(did,owner,kb,chunks,store,checkpoint=lambda:checkpoint(jid,token,50))
            dimensions=None
        else:
            for i in range(0,len(chunks),32):
                checkpoint(jid,token,35+int(45*i/len(chunks)))
                vectors.extend(providers.embed([c['text'] for c in chunks[i:i+32]]))
            checkpoint(jid,token,85)
            providers.delete_vectors(did)
            store.put_json('documents/'+did+'/index-execution.json',snapshot)
            providers.put_vectors(did,owner,kb,chunks,vectors)
            dimensions=len(vectors[0])
        try:checkpoint(jid,token,95)
        except InterruptedError:
            providers.delete_vectors(did)
            raise
        store.put_json('documents/'+did+'/index-execution.json',snapshot)
        store.put_json('documents/'+did+'/index.json',{'dataset_id':snapshot['dataset_id'],'index_generation':snapshot['index_generation'],'model_selection':routing.public_selection(snapshot),'search_provider':cfg['search_provider'],'fingerprint':providers.fingerprint(),'dimensions':dimensions,'chunk_count':len(chunks),'indexed_at':time.time(),'embedding_provider':cfg['embedding_provider'],'embedding_model':cfg['embedding_model']})
    elif kind=='extract':
        data=store.json(ref)
        if cfg['model_provider'] in ('openai','oci') and not data.get('allow_external'):raise ValueError('External extraction requires explicit external data transmission consent')
        sources=[]
        with Session() as s:
            for doc_id in data['document_ids']:
                d=s.get(Record,doc_id)
                if not d or d.owner!=owner or d.status!='ready' or d.parent_id!=snapshot['dataset_id']:raise ValueError('An extraction document is unavailable, outside the dataset, or not ready')
                if not routing.index_matches(d,snapshot):raise ValueError('Dataset index changed since extraction was submitted; run extraction again.')
                for c in store.json('documents/'+doc_id+'/chunks.json')['chunks']:sources.append({'document_id':doc_id,'document_name':d.name,**c})
        text='\n\n'.join(f'Document: {c["document_name"]}; chunk {c["id"]}; page {c["page"]}\n{c["text"]}' for c in sources)
        if len(text)>200000:raise ValueError('Extraction exceeds 200,000 character context limit; choose fewer documents')
        result,evidence=providers.extract_with_evidence(text,data['schema'],sources)
        from jsonschema import validate
        validate(result,data['schema']);checkpoint(jid,token,90)
        data.update(result=result,evidence=evidence,evidence_notice='Review all values. Evidence contains only validated verbatim source quotes; fields without evidence are unverified.',sources=[{'document_id':c['document_id'],'document_name':c['document_name'],'chunk_id':c['id'],'page':c['page'],'excerpt':c['text'][:1000]} for c in sources],review_status='unreviewed',completed_at=time.time(),mock=cfg['model_provider']=='mock')
        store.put_json(ref,data)
    else:raise ValueError('Unknown job type')
    with Session.begin() as s:
        j=s.get(Job,jid)
        if j.status!='running' or j.lease_token!=token:raise InterruptedError('Job cancelled')
        r=s.get(Record,did)
        if r:r.status='ready';r.error='';r.updated_at=time.time()
        j.status='completed';j.progress=100;j.error='';j.updated_at=time.time();j.lease_until=0

def run_once():
    from .queue_transport import get_transport
    global _last_reconcile
    transport=get_transport(settings()['queue_provider']);delivery=None;claimed=None
    now=time.monotonic()
    if now-_last_reconcile>=30:
        _last_reconcile=now;claimed=claim()
    if not claimed:
        delivery=transport.receive(timeout=0)
        claimed=claim(delivery.job_id) if delivery else None
    if delivery and not claimed:
        with Session() as session:
            existing=session.get(Job,delivery.job_id)
            if existing:transport.ack_terminal(delivery,existing.status)
    if not claimed:claimed=claim()
    if not claimed:return False
    jid,token=claimed
    stop=threading.Event()
    def heartbeat():
        while not stop.wait(20):
            try:
                with Session.begin() as session:
                    job=session.get(Job,jid)
                    if not job or job.lease_token!=token or job.status!='running':return
                    job.lease_until=time.time()+900
                if delivery and delivery.job_id==jid:transport.renew(delivery)
            except Exception:pass
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    try:
        with Session() as session:target_id=session.get(Job,jid).target_id
        with document_lock(target_id):process(jid,token)
    except InterruptedError:pass
    except Exception as e:
        # Never log request bodies or provider secrets. Curated error classes only.
        message=str(e)[:400] if isinstance(e,(ValueError,providers.ProviderError)) else 'Processing failed; inspect service health and retry'
        with Session.begin() as s:
            j=s.get(Job,jid)
            if j and j.status=='running' and j.lease_token==token:
                j.status='failed';j.error=message;j.updated_at=time.time();j.lease_until=0
                r=s.get(Record,j.target_id)
                if r:r.status='failed';r.error=message
    finally:
        stop.set();thread.join(timeout=1)
        if delivery and delivery.job_id==jid:
            with Session() as session:finished=session.get(Job,jid)
            if finished:transport.ack_terminal(delivery,finished.status)
    return True

if __name__=='__main__':
    init()
    while True:
        if not run_once():time.sleep(2)
