"""Gemini Developer API through its OpenAI-compatible endpoint."""
import copy
from jsonschema import validate, ValidationError
from ...validation import ConnectionError
from ..ags_openai.adapter import generate
from ..ags_openai import adapter


def agent_tools(tools):
    """Declare union branches as separate functions without widening contracts."""
    result=[]
    for tool in tools:
        function=tool.get('function',{})
        branches=function.get('parameters',{}).get('oneOf')
        if not branches:
            result.append(copy.deepcopy(tool));continue
        for index, branch in enumerate(branches):
            if branch.get('type')!='object':raise ConnectionError('Gemini function alternatives must be object schemas.')
            value=copy.deepcopy(tool);f=value['function']
            f['name']=function['name']+'__branch_'+str(index)
            f['parameters']=copy.deepcopy(branch)
            for prop in f['parameters'].get('properties',{}).values():
                if 'const' in prop:prop['enum']=[prop.pop('const')]
            result.append(value)
    return result


def agent_calls(calls, tools):
    declarations={}
    for tool in tools:
        function=tool['function'];name=function['name'];schema=function['parameters']
        branches=schema.get('oneOf')
        if branches:
            for index,branch in enumerate(branches):declarations[name+'__branch_'+str(index)]=(name,branch)
        else:declarations[name]=(name,schema)
    result=[]
    for call in calls:
        if call['name'] not in declarations:raise ConnectionError('Gemini returned an undeclared function.')
        name,schema=declarations[call['name']]
        try:validate(call['arguments'],schema)
        except ValidationError:raise ConnectionError('Gemini returned invalid function arguments. Retry the request.') from None
        result.append(dict(call,name=name))
    return result


def embed(connection, texts, query, dim, extra):
    # Gemini protobuf JSON omits the default zero index; other order checks stay strict.
    return adapter.embed(connection, texts, query, dim, extra, restore_zero_index=True)
