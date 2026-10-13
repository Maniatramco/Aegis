"""Native Oracle vectors behind the existing bounded vector-store contract.

One table holds namespaced document and unified-knowledge vectors. SQL filters
scope candidates before distance ranking; canonical sources still authorize hits.
"""
import array
import json
import math
import time
from types import SimpleNamespace as NS
from contextlib import contextmanager

TABLE='aegis_knowledge_vectors'
DDL='''CREATE TABLE aegis_knowledge_vectors (
 collection_name VARCHAR2(100) NOT NULL, point_id VARCHAR2(100) NOT NULL,
 source_type VARCHAR2(32), owner_id VARCHAR2(80), dataset_id VARCHAR2(80),
 entity_id VARCHAR2(180), document_id VARCHAR2(80), source_version NUMBER,
 dimensions NUMBER, payload_json CLOB NOT NULL, embedding VECTOR(*, FLOAT32),
 updated_at BINARY_DOUBLE NOT NULL,
 CONSTRAINT pk_aegis_knowledge_vectors PRIMARY KEY(collection_name,point_id))'''

def prepare(engine):
    from sqlalchemy import inspect
    if TABLE not in inspect(engine).get_table_names():
        with engine.connect() as connection:
            connection.exec_driver_sql(DDL)
            connection.exec_driver_sql('CREATE INDEX ix_aegis_vectors_scope ON aegis_knowledge_vectors(collection_name,dataset_id,document_id)')

def parsed(value):return json.loads(value.read() if hasattr(value,'read') else value)

class OracleVectors:
    def __init__(self,engine=None):
        from .database_control import active_engine
        self.engine=engine or active_engine()

    @contextmanager
    def cursor(self,write=False):
        connection=self.engine.raw_connection()
        try:
            with connection.cursor() as cursor:yield cursor
            if write:connection.commit()
        except Exception:
            if write:connection.rollback()
            raise
        finally:connection.close()

    def collection_exists(self,name):
        with self.cursor() as c:
            c.execute('SELECT 1 FROM '+TABLE+' WHERE collection_name=:name AND point_id=\'__collection__\'',name=name)
            return c.fetchone() is not None

    def create_collection(self,name,vectors_config):
        if self.collection_exists(name):return
        from qdrant_client.models import PointStruct
        # Marker is excluded from every retrieval and point count.
        self.upsert(name,[NS(id='__collection__',vector=None,payload={'size':vectors_config.size,'distance':'Cosine'})])

    def create_payload_index(self,*args,**kwargs):return True

    def get_collections(self):
        with self.cursor() as c:
            c.execute("SELECT collection_name FROM "+TABLE+" WHERE point_id='__collection__' ORDER BY collection_name")
            return NS(collections=[NS(name=r[0]) for r in c.fetchall()])

    def get_collection(self,name):
        from qdrant_client.models import VectorParams,Distance
        with self.cursor() as c:
            c.execute("SELECT payload_json FROM "+TABLE+" WHERE collection_name=:name AND point_id='__collection__'",name=name)
            row=c.fetchone()
            if not row:raise ValueError('Vector namespace does not exist.')
            data=parsed(row[0])
            c.execute("SELECT COUNT(*) FROM "+TABLE+" WHERE collection_name=:name AND point_id<>'__collection__'",name=name)
            count=c.fetchone()[0]
            return NS(points_count=count,config=NS(params=NS(vectors=VectorParams(size=data['size'],distance=Distance.COSINE))))

    def upsert(self,name,points,wait=True):
        if not points:return
        rows=[]
        expected=self.get_collection(name).config.params.vectors.size if any(p.vector is not None for p in points) else None
        for point in points:
            p=point.payload or {};vector=point.vector
            if vector is not None:
                if len(vector)!=expected or not all(math.isfinite(v) for v in vector):raise ValueError('Vector dimensions or values do not match the embedding namespace.')
            rows.append({'collection_name':name,'point_id':str(point.id),
                'source_type':p.get('source_type','document_chunk'),'owner_id':p.get('owner_id',p.get('owner')),
                'dataset_id':p.get('dataset_id',p.get('kb_id')),'entity_id':p.get('entity_id'),
                'document_id':p.get('document_id'),'source_version':p.get('source_version',p.get('index_version')) if isinstance(p.get('source_version',p.get('index_version')),int) else None,
                'dimensions':len(vector) if vector is not None else None,'payload_json':json.dumps(p,ensure_ascii=False),
                'embedding':array.array('f',vector) if vector is not None else None,'updated_at':time.time()})
        columns=list(rows[0]);updates=','.join('t.'+k+'=:'+k for k in columns if k not in ('collection_name','point_id'))
        sql='MERGE INTO '+TABLE+' t USING (SELECT :collection_name collection_name,:point_id point_id FROM dual) s ON (t.collection_name=s.collection_name AND t.point_id=s.point_id) WHEN MATCHED THEN UPDATE SET '+updates+' WHEN NOT MATCHED THEN INSERT ('+','.join(columns)+') VALUES ('+','.join(':'+k for k in columns)+')'
        with self.cursor(write=True) as c:
            import oracledb
            c.setinputsizes(payload_json=oracledb.DB_TYPE_CLOB)
            c.executemany(sql,rows)
        return True

    def where(self,name,filter=None,ids=None):
        clauses=["collection_name=:collection","point_id<>'__collection__'"];values={'collection':name}
        def members(column,items):
            if not items:return '1=0'
            groups=[]
            for start in range(0,len(items),500):
                keys=[]
                for item in items[start:start+500]:
                    key='p'+str(len(values));values[key]=str(item);keys.append(':'+key)
                groups.append(column+' IN ('+','.join(keys)+')')
            return '('+' OR '.join(groups)+')'
        fields={'owner':'owner_id','owner_id':'owner_id','dataset_id':'dataset_id','document_id':'document_id','entity_id':'entity_id','source_type':'source_type'}
        if ids is not None:clauses.append(members('point_id',list(ids)))
        for condition in (getattr(filter,'must',None) or []):
            if hasattr(condition,'has_id'):clauses.append(members('point_id',condition.has_id));continue
            key=getattr(condition,'key',None)
            if key not in fields:raise ValueError('Unsupported vector scope filter.')
            match=condition.match
            items=getattr(match,'any',None)
            clauses.append(members(fields[key],items if items is not None else [match.value]))
        if getattr(filter,'must_not',None) or getattr(filter,'should',None):raise ValueError('Unsupported vector scope filter.')
        return ' AND '.join(clauses),values

    def query_points(self,name,query,query_filter=None,limit=5):
        where,values=self.where(name,query_filter)
        values.update(vector=array.array('f',query),dimensions=len(query))
        limit=max(1,min(100,int(limit)))
        sql='SELECT point_id,payload_json,VECTOR_DISTANCE(embedding,:vector,COSINE) distance FROM '+TABLE+' WHERE '+where+' AND dimensions=:dimensions ORDER BY distance,point_id FETCH FIRST '+str(limit)+' ROWS ONLY'
        with self.cursor() as c:
            c.execute(sql,values)
            return NS(points=[NS(id=r[0],payload=parsed(r[1]),score=1-float(r[2])) for r in c.fetchall()])

    def scroll(self,name,scroll_filter=None,limit=100,offset=None,with_payload=True,with_vectors=False):
        where,values=self.where(name,scroll_filter)
        if offset is not None:where+=' AND point_id>:offset';values['offset']=str(offset)
        limit=max(1,min(1000,int(limit)))
        with self.cursor() as c:
            c.execute('SELECT point_id,payload_json'+(',embedding' if with_vectors else '')+' FROM '+TABLE+' WHERE '+where+' ORDER BY point_id FETCH FIRST '+str(limit+1)+' ROWS ONLY',values)
            rows=c.fetchall();more=len(rows)>limit;rows=rows[:limit]
            return ([NS(id=r[0],payload=parsed(r[1]) if with_payload else None,vector=list(r[2]) if with_vectors else None) for r in rows],rows[-1][0] if more else None)

    def delete(self,name,points_selector,wait=True):
        ids=getattr(points_selector,'points',None)
        where,values=self.where(name,getattr(points_selector,'filter',None),ids)
        with self.cursor(write=True) as c:c.execute('DELETE FROM '+TABLE+' WHERE '+where,values)
        return True

    def delete_collection(self,name):
        with self.cursor(write=True) as c:c.execute('DELETE FROM '+TABLE+' WHERE collection_name=:name',name=name)
        return True

    def count(self,name,count_filter=None,exact=True):
        where,values=self.where(name,count_filter)
        with self.cursor() as c:
            c.execute('SELECT COUNT(*) FROM '+TABLE+' WHERE '+where,values)
            return NS(count=c.fetchone()[0])
