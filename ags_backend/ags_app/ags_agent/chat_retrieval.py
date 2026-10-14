"""Bounded keyword/vector fusion over the same authorized published points.

The local publication manifest supplies keyword ranking signals only. Answer
evidence is fetched from the active vector provider and digest-verified by the
published view. No new Oracle index, canonical-file reads or query-time writes.
"""
import math
import re
from collections import Counter


def terms(text):
    return re.findall(r'[^\W_]+(?:[+#.][^\W_]+)*',text.casefold(),re.UNICODE)


def keyword_ranks(query,points,limit):
    query_terms=set(terms(query))
    if not query_terms or not points:return []
    counts={id:Counter(terms(p.get('title','')+' '+p['text'])) for id,p in points.items()}
    lengths={id:sum(c.values()) for id,c in counts.items()}
    average=sum(lengths.values())/max(1,len(counts)) or 1
    frequency={t:sum(t in c for c in counts.values()) for t in query_terms}
    scores={}
    for id,c in counts.items():
        score=0.0
        for t in query_terms:
            n=c.get(t,0)
            if n:
                weight=math.log(1+(len(counts)-frequency[t]+.5)/(frequency[t]+.5))
                score+=weight*n*2.2/(n+1.2*(.25+.75*lengths[id]/average))
        if score:scores[id]=score
    return sorted(scores,key=lambda id:(-scores[id],id))[:limit]


def fuse(vector_ids,keyword_ids,points,limit):
    # Fuse complete entities, not fragments, so a long record cannot take all
    # candidate slots. Keep each retriever's best rank for an entity.
    scores={}
    for ranked in (vector_ids,keyword_ids):
        seen=set()
        for rank,id in enumerate(ranked,1):
            entity=points[id]['entity_id']
            if entity in seen:continue
            seen.add(entity);scores[entity]=scores.get(entity,0)+1/(60+rank)
    return sorted(scores,key=lambda entity:(-scores[entity],entity))[:limit]
