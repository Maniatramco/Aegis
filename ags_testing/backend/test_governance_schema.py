"""Prevent content or unrelated database objects entering the OCI schema publisher."""
import copy
import importlib.util
from pathlib import Path
import pytest

path=Path(__file__).resolve().parents[2]/'ags_deploy/scripts/publish-governance-schema.py'
spec=importlib.util.spec_from_file_location('governance_schema_publisher',path)
publisher=importlib.util.module_from_spec(spec);spec.loader.exec_module(publisher)


def snapshot():
    return {'owner':'ADMIN','captured_at':1792340334,'source':'Read-only synthetic schema',
            'tables':[{'name':name,'columns':[{'name':'ID','data_type':'VARCHAR2(80)','nullable':False,'position':1}],
                       'primary_key':['ID'],'foreign_keys':[]} for name in sorted(publisher.TABLES)]}


def test_accepts_only_complete_workflow_schema_definitions():
    value=snapshot();assert publisher.validate(value)==value
    value['tables'].pop()
    with pytest.raises(ValueError,match='all eight'):publisher.validate(value)


@pytest.mark.parametrize('location',['snapshot','table','column'])
def test_rejects_data_values_and_unrelated_fields(location):
    value=snapshot()
    target={'snapshot':value,'table':value['tables'][0],'column':value['tables'][0]['columns'][0]}[location]
    target['rows']=[{'private_value':'Never publish'}]
    with pytest.raises(ValueError):publisher.validate(value)


def test_rejects_unrelated_tables_and_duplicates():
    value=snapshot();value['tables'][0]['name']='SESSIONS_TBL'
    with pytest.raises(ValueError):publisher.validate(value)
    value=snapshot();value['tables'][1]=copy.deepcopy(value['tables'][0])
    with pytest.raises(ValueError,match='Duplicate'):publisher.validate(value)
