"""Reject unsupported interpretations; never choose another route by keywords."""
import re
from difflib import SequenceMatcher

COMMAND_HELP='Choose @Onboard, @Upload, @Extract or @ReExtract from the agent menu, then add your request.'
CLARIFY='What would you like me to do or look up? Please name the task or information you need.'


def input_problem(text):
    value=text.strip()
    if value.startswith('@') and not re.match(r'^@(onboard|upload|extract|reextract)(?=\s|$)',value,re.I):
        return COMMAND_HELP
    if value and not any(c.isalnum() for c in value):
        return 'Please enter a question or choose @Onboard, @Upload, @Extract or @ReExtract.'
    return None


def request_clarification(text):
    problem=input_problem(text)
    if problem:return problem
    value=re.sub(r'[.!?]+$','',text.strip().casefold()).strip()
    if value in {'do it','do that','go ahead','continue','that one','this one','show me','tell me','what','why','yes','no','please'}:
        return CLARIFY
    return None


# These are evidence checks on an already selected metadata category, not
# routing rules. Minor spelling errors are accepted; an absent topic asks the
# user to clarify instead of silently substituting a dataset-status answer.
TOPICS={
    'document_count':{'document','documents','doc','docs','file','files','pdf','pdfs','uploaded','attachments'},
    'documents':{'document','documents','doc','docs','file','files','filename','filenames','upload','uploaded','resume','pdf','attachments','names'},
    'datasets':{'dataset','datasets','collection','collections','repository','repositories'},
    'prompts':{'prompt','prompts','template','templates','schema'},
    'models':{'model','models','llm','embedding','tokens','token','context','provider','configuration','mapping'},
    'status':{'status','progress','state','ready','failed','failure','complete','completed','finished','done','pending','processing','indexing','indexed','running','processed','working','active','happened'},
    'workflow':{'workflow','workflows','onboard','onboarding','progress','status','stage','steps','job','jobs','processing','finished','done','completed','state'},
}


def route_problem(text, decision):
    problem=request_clarification(text)
    if problem:return problem
    quote=decision.get('request_evidence','')
    normalize=lambda value:' '.join(value.casefold().split())
    if not isinstance(quote,str) or not quote.strip() or normalize(quote) not in normalize(text):
        return CLARIFY
    query=decision.get('query')
    if decision.get('agent')=='chat' and query in TOPICS:
        # Preserve semantic routing for non-English requests; literal evidence
        # validation still applies. English catalog shortcuts need a topic.
        if any(c.isalpha() and not c.isascii() for c in text):return None
        words=re.findall(r'[a-z]+',text.casefold())
        if query in ('document_count','documents') and any(w in {'prompt','prompts','template','templates'} for w in words) and not any(w in {'document','documents','pdf','pdfs'} for w in words):
            return 'Are you asking about prompt templates or uploaded documents?'
        topics=TOPICS[query]
        if not any(word in topics or len(word)>=5 and any(len(topic)>=5 and SequenceMatcher(None,word,topic).ratio()>=.82 for topic in topics) for word in words):
            return 'Please clarify what you want to check. Are you asking about documents, saved results, models, or workflow status?'
    if decision.get('agent') in ('onboard_extract','reextract') and re.match(r'^\s*(how\b|why\b|what\b|explain\b|can\s+i\b|can\s+we\b)',text,re.I):
        return 'Do you want instructions for this workflow, or do you want to run it?'
    return None
