"""Live native-vector contract check in an isolated, removable test namespace."""
import json
import uuid
from ags_app import core,relational,oracle_vectors,database_control
from qdrant_client.models import VectorParams,Distance,PointStruct,Filter,FieldCondition,MatchValue,HasIdCondition,PointIdsList

receipt=database_control.prepare(core.engine)
assert receipt['schema_ready'] and receipt['tables_present']==13
client=oracle_vectors.OracleVectors(core.engine)
name='aegis_qa_oracle_'+uuid.uuid4().hex[:12]
try:
    client.create_collection(name,VectorParams(size=2,distance=Distance.COSINE))
    ids=[str(uuid.uuid4()) for _ in range(3)]
    client.upsert(name,[PointStruct(id=id,vector=vector,payload={'owner':owner,'dataset_id':dataset,'document_id':'test-document','text':'Fictional native vector fixture'}) for id,vector,owner,dataset in zip(ids,[[1,0],[.9,.1],[0,1]],['alice','bob','alice'],['dataset-one','dataset-one','dataset-two'])])
    scope=Filter(must=[FieldCondition(key='owner',match=MatchValue(value='alice')),FieldCondition(key='dataset_id',match=MatchValue(value='dataset-one'))])
    hits=client.query_points(name,[1,0],query_filter=scope,limit=5).points
    assert len(hits)==1 and hits[0].id==ids[0] and abs(hits[0].score-1)<1e-6
    hits=client.query_points(name,[1,0],query_filter=Filter(must=[HasIdCondition(has_id=[ids[2]])]),limit=5).points
    assert len(hits)==1 and hits[0].id==ids[2]
    first,offset=client.scroll(name,limit=1,with_vectors=True)
    assert len(first)==1 and offset is not None and len(first[0].vector)==2
    rest,offset=client.scroll(name,offset=offset,limit=10,with_vectors=True)
    assert len(rest)==2 and offset is None
    assert client.get_collection(name).points_count==3
    client.upsert(name,[PointStruct(id=ids[0],vector=[1,0],payload={'owner':'alice','dataset_id':'dataset-one','document_id':'test-document','text':'Updated fictional fixture'})])
    assert client.get_collection(name).points_count==3
    client.delete(name,PointIdsList(points=[ids[1]]))
    assert client.count(name).count==2
    print(json.dumps(dict(receipt,native_search=True,authorization_filters=True,allowed_id_filter=True,pagination=True,idempotent_upsert=True,deletion=True,active_database=database_control.public()['active_provider'],active_vector_provider=core.settings()['search_provider']),indent=2))
finally:client.delete_collection(name)
