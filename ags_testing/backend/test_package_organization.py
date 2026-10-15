"""Import compatibility and provider dispatch protect saved model integrations."""
import importlib
import pytest
from ags_app.ags_models import provider_registry
from ags_app.ags_models.validation import ConnectionError


@pytest.mark.parametrize('old,new',[
    ('agent_graph','ags_agent.agent_graph'),
    ('agent_model','ags_agent.agent_model'),
    ('agent_workspace','ags_agent.agent_workspace'),
    ('chat_agent','ags_agent.chat_agent'),
    ('token_usage','ags_agent.token_usage'),
    ('model_connections','ags_models.connection'),
    ('model_registration','ags_models.registration'),
    ('model_parameters','ags_models.parameters'),
    ('ollama_provider','ags_models.providers.ags_local.ollama'),
    ('oci_models','ags_models.providers.ags_oci.enterprise'),
])
def test_legacy_imports_resolve_to_the_same_module(old,new):
    assert importlib.import_module('ags_app.'+old) is importlib.import_module('ags_app.'+new)


@pytest.mark.parametrize('protocol,endpoint,suffix',[
    ('openai-compatible','https://api.openai.com/v1','ags_openai.adapter'),
    ('openai-compatible','https://generativelanguage.googleapis.com/v1beta/openai','ags_gcp.gemini'),
    ('azure-openai','https://example.openai.azure.com/openai/v1','ags_azure.adapter'),
    ('vertex','https://aiplatform.googleapis.com','ags_gcp.vertex'),
    ('bedrock','https://bedrock-runtime.us-east-1.amazonaws.com','ags_aws.bedrock'),
    ('oci','https://inference.generativeai.us-chicago-1.oci.oraclecloud.com','ags_oci.native'),
])
def test_provider_selection_is_explicit_and_does_not_load_cloud_sdks(monkeypatch,protocol,endpoint,suffix):
    import builtins
    original=builtins.__import__
    def restricted(name,*args,**kwargs):
        if name.split('.')[0] in ('boto3','google','oci'):
            raise AssertionError('Provider selection attempted to load '+name)
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',restricted)
    selected=provider_registry.provider({'protocol':protocol,'endpoint':endpoint})
    assert selected.__name__.endswith(suffix)
    assert callable(selected.generate) and callable(selected.embed)


def test_unknown_protocol_cannot_become_an_import_path():
    with pytest.raises(ConnectionError,match='supported connection protocol'):
        provider_registry.provider({'protocol':'os.system','endpoint':'https://example.com'})


def test_legacy_registry_cli_still_exposes_the_operator_command():
    import subprocess,sys
    result=subprocess.run([sys.executable,'-m','ags_app.model_registry','--help'],
                          capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    assert '--embedding' in result.stdout and '--apply' in result.stdout
