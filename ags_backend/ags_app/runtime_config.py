"""Typed, non-secret settings from one TOML file, shared by API and worker."""
import argparse
import json
import os
import re
import tomllib
from functools import lru_cache
from pathlib import Path

DEFAULT_FILE = Path(__file__).with_name('ags_config') / 'runtime.toml'


class ConfigurationError(ValueError):
    pass


@lru_cache(maxsize=16)
def _document(filename):
    try:
        with Path(filename).open('rb') as source:doc=tomllib.load(source)
    except (OSError,tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError('Cannot read the Aegis runtime configuration file.') from exc
    if doc.get('schema_version')!=1:
        raise ConfigurationError('Unsupported Aegis runtime configuration schema_version.')
    settings={};sections={}
    for section,values in doc.items():
        if section in ('schema_version','profiles','bounds','choices','numeric_strings'):continue
        if not isinstance(values,dict):raise ConfigurationError('Invalid runtime configuration section: '+section)
        for name,value in values.items():
            if (not re.fullmatch(r'AEGIS_[A-Z0-9_]+',name) or name in settings
                    or re.search(r'PASSWORD|SECRET|CREDENTIAL|API_KEY|PRIVATE_KEY|ACCESS_KEY|(?:^|_)TOKEN(?:_|$)',name)
                    or type(value) not in (bool,int,str)):
                raise ConfigurationError('Invalid or sensitive runtime setting name: '+name)
            settings[name]=value;sections[name]=section
    for table in ('bounds','choices','numeric_strings'):
        for name,values in doc.get(table,{}).items():
            if name not in settings or not isinstance(values,list) or not values:
                raise ConfigurationError('Invalid configuration '+table+' for '+name)
            if table in ('bounds','numeric_strings') and (type(settings[name]) is not (int if table=='bounds' else str) or len(values)!=2
                    or any(type(v) is not int for v in values) or values[0]>values[1]):
                raise ConfigurationError('Invalid configuration bounds for '+name)
    for profile,values in doc.get('profiles',{}).items():
        if not isinstance(values,dict) or set(values)-set(settings):
            raise ConfigurationError('Invalid runtime configuration profile: '+profile)
        for name,value in values.items():_validate(name,value,settings,doc)
    for name,value in settings.items():_validate(name,value,settings,doc)
    return doc,settings,sections


def _validate(name,value,defaults,doc):
    if name not in defaults:raise ConfigurationError('Unknown runtime setting: '+name)
    if type(value) is not type(defaults[name]):
        raise ConfigurationError('Wrong value type for '+name)
    limits=doc.get('bounds',{}).get(name)
    if limits and not limits[0]<=value<=limits[1]:
        raise ConfigurationError('Invalid '+name+': expected '+str(limits[0])+' through '+str(limits[1]))
    choices=doc.get('choices',{}).get(name)
    if choices and value not in choices:raise ConfigurationError('Unsupported value for '+name)
    numeric=doc.get('numeric_strings',{}).get(name)
    if numeric and value and (not value.isdecimal() or not numeric[0]<=int(value)<=numeric[1]):
        raise ConfigurationError('Invalid numeric setting '+name)
    return value


def _selection():
    filename=os.environ.get('AEGIS_CONFIG_FILE') or str(DEFAULT_FILE)
    doc,defaults,sections=_document(filename)
    profile=os.getenv('AEGIS_CONFIG_PROFILE','default')
    if profile not in ('','default') and profile not in doc.get('profiles',{}):
        raise ConfigurationError('Unknown Aegis runtime configuration profile: '+profile)
    return filename,profile,doc,defaults,sections


def get(name):
    _,profile,doc,defaults,_=_selection()
    if name not in defaults:raise ConfigurationError('Unknown runtime setting: '+name)
    value=doc.get('profiles',{}).get(profile,{}).get(name,defaults[name])
    if name in os.environ:
        raw=os.environ[name]
        if type(value) is bool:
            if raw.lower() not in ('true','false','1','0','yes','no'):
                raise ConfigurationError('Invalid boolean for '+name)
            value=raw.lower() in ('true','1','yes')
        elif type(value) is int:
            if not raw.isdecimal():raise ConfigurationError('Invalid integer for '+name)
            value=int(raw)
        else:value=raw
    return _validate(name,value,defaults,doc)


def bounds(name):
    _,_,doc,_,_=_selection()
    try:return tuple(doc['bounds'][name])
    except KeyError:raise ConfigurationError('No configured bounds for '+name) from None


def snapshot():
    filename,profile,_,defaults,sections=_selection()
    values={}
    for name in defaults:values.setdefault(sections[name],{})[name]=get(name)
    return {'file':filename,'profile':profile or 'default','values':values,
            'environment_overrides':[name for name in defaults if name in os.environ]}


def validate():
    data=snapshot();v={k:value for group in data['values'].values() for k,value in group.items()}
    if v['AEGIS_CHUNK_OVERLAP']>=v['AEGIS_CHUNK_SIZE']:
        raise ConfigurationError('AEGIS_CHUNK_OVERLAP must be smaller than AEGIS_CHUNK_SIZE.')
    if v['AEGIS_CHAT_CONTEXT_TOKENS']<=v['AEGIS_CHAT_OUTPUT_TOKENS']+v['AEGIS_CONTEXT_HEADROOM_TOKENS']:
        raise ConfigurationError('Chat context must reserve space for the answer and headroom.')
    if v['AEGIS_WORKER_HEARTBEAT_SECONDS']*2>=v['AEGIS_WORKER_LEASE_SECONDS']:
        raise ConfigurationError('Worker lease must exceed two heartbeat intervals.')
    if v['AEGIS_OCR_CONTEXT']<v['AEGIS_OCR_MAX_TOKENS']+v['AEGIS_OCR_INPUT_HEADROOM_TOKENS']:
        raise ConfigurationError('OCR context must reserve the configured OCR input headroom.')
    return data



def model_defaults():
    """Public numeric form defaults; per-model saved values still win."""
    return {'context_limit':get('AEGIS_DEFAULT_MODEL_CONTEXT_TOKENS'),
            'embedding_context_limit':get('AEGIS_DEFAULT_EMBEDDING_INPUT_TOKENS'),
            'max_output_tokens':get('AEGIS_DEFAULT_MODEL_OUTPUT_TOKENS'),
            'timeout':get('AEGIS_MODEL_REGISTRATION_TIMEOUT'),
            'headroom_tokens':get('AEGIS_CONTEXT_HEADROOM_TOKENS'),
            'context_max':bounds('AEGIS_DEFAULT_MODEL_CONTEXT_TOKENS')[1],
            'output_max':bounds('AEGIS_DEFAULT_MODEL_OUTPUT_TOKENS')[1],
            'timeout_min':bounds('AEGIS_MODEL_REGISTRATION_TIMEOUT')[0],
            'timeout_max':bounds('AEGIS_MODEL_REGISTRATION_TIMEOUT')[1]}


def install(app,auth):
    from fastapi import Depends
    @app.get('/api/runtime-config')
    def inspect_runtime_config(owner=Depends(auth)):
        from .dataset_access import require_admin
        require_admin(owner)
        return snapshot()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file',type=Path)
    parser.add_argument('--profile')
    args=parser.parse_args()
    if args.file:os.environ['AEGIS_CONFIG_FILE']=str(args.file.resolve())
    if args.profile is not None:os.environ['AEGIS_CONFIG_PROFILE']=args.profile
    try:print(json.dumps(validate(),indent=2))
    except ConfigurationError as exc:parser.exit(2,str(exc)+'\n')


if __name__=='__main__':main()
