"""Exercise real foreign keys and transactional audit fields through workflows."""
import pytest
from sqlalchemy import event, text, select, update
from sqlalchemy.exc import IntegrityError
from ags_app import core, relational, worker
from test_dataset_models import system, dataset, upload, template, post

def enforce_fk(s):
    engine=s.session.kw['bind']
    @event.listens_for(engine,'connect')
    def enable(connection,record):connection.execute('PRAGMA foreign_keys=ON')
    with engine.connect() as c:c.execute(text('PRAGMA foreign_keys=ON'))
    with s.session.begin() as db:
        db.add(core.User(id='alice',username='relational-alice',password_hash=core.password_hash('Test-password-123')))
    return engine

def test_owned_dataset_models_upload_extract_and_review_audits(system):
    s=system;enforce_fk(s)
    d=dataset(s);doc=upload(s,d)['documents'][0];prompt=template(s)
    e=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':prompt['id']})
    assert worker.run_once()
    result=s.api.get('/api/extractions/'+e['id']).json()
    saved=s.api.patch('/api/extractions/'+e['id'],json={'version':result['version'],'result':{'owner':'Reviewed Alice'}})
    assert saved.status_code==200,saved.text
    with s.session() as db:
        entity=db.get(relational.Dataset,d['id']);assert entity.created_by=='alice' and entity.created_via=='api'
        mappings=db.scalars(select(relational.DatasetModel).where(relational.DatasetModel.dataset_id==d['id'])).all()
        assert {m.category for m in mappings}=={'chat','extraction','embedding'}
        assert all(m.is_default for m in mappings)
        document=db.get(relational.Document,doc['id']);assert document.dataset_id==d['id'] and document.updated_via=='worker'
        ext=db.get(relational.Extraction,e['id']);assert ext.document_id==doc['id'] and ext.prompt_id==prompt['id']
        assert ext.status=='ready' and ext.version==2 and ext.updated_by=='alice'
        assert ext.filename==doc['name']
        reviews=db.scalars(select(relational.Review).where(relational.Review.extract_id==e['id'])).all()
        assert len(reviews)==1 and reviews[0].extraction_version==1 and reviews[0].review_version==2
        assert reviews[0].created_by=='alice' and reviews[0].reviewed_result_reference==saved.json()['output_reference']
        job=db.scalar(select(core.Job).where(core.Job.target_id==e['id']))
        assert job.extract_id==e['id'] and job.document_id is None and job.updated_via=='worker'

def test_database_rejects_invalid_dataset_and_multiple_job_targets(system):
    s=system;engine=enforce_fk(s);d=dataset(s);doc=upload(s,d)['documents'][0];prompt=template(s)
    e=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':prompt['id']})
    with pytest.raises(IntegrityError),engine.begin() as c:
        c.execute(update(relational.Document).where(relational.Document.document_id==doc['id']).values(dataset_id='missing'))
    with pytest.raises(IntegrityError),engine.begin() as c:
        c.execute(update(core.Job).where(core.Job.target_id==e['id']).values(document_id=doc['id']))

def test_review_history_survives_reextract_and_document_deletion(system):
    s=system;enforce_fk(s);d=dataset(s);doc=upload(s,d)['documents'][0];prompt=template(s)
    e=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':prompt['id']});assert worker.run_once()
    first=s.api.patch('/api/extractions/'+e['id'],json={'version':1,'result':{'owner':'First review'}}).json()
    assert first['version']==2
    assert s.api.post('/api/extractions/'+e['id']+'/reextract',json={'version':2,'confirm_reviewed':True}).status_code==409
    rerun=post(s,'/api/extractions',{'dataset_id':d['id'],'document_ids':[doc['id']],'template_id':prompt['id']});assert worker.run_once()
    second=s.api.patch('/api/extractions/'+rerun['id'],json={'version':1,'result':{'owner':'Second review'}})
    assert second.status_code==200,second.text
    with s.session() as db:
        assert len(db.scalars(select(relational.Review).where(relational.Review.extract_id.in_([e['id'],rerun['id']]))).all())==2
    assert s.api.delete('/api/documents/'+doc['id']).status_code==200
    with s.session() as db:
        assert db.get(relational.Document,doc['id']) is None
        assert db.get(relational.Extraction,e['id']).document_id is None
        assert db.scalar(select(core.Job).where(core.Job.target_id==doc['id'])).document_id is None
