"""Explicit, administrator-only publication of metadata to OCI Data Catalog."""
import json
import os
import time
import uuid
from datetime import datetime, timezone
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from . import core, governance

CONFIG = 'configuration/governance-oci.json'
STATE = 'configuration/governance-oci-status.json'
CONCEPTS = {
    'Dataset': 'An Aegis collection of documents, prompts and saved results governed by dataset access assignments.',
    'Document': 'An original source file registered in an Aegis dataset. Its original content remains in the configured file store.',
    'Extraction': 'A saved processing run linked to its source documents, prompt version and recorded model selection.',
    'Prompt': 'A versioned extraction instruction and output schema. Saved runs retain the version they used.',
    'Review': 'A saved review revision linked to the extraction version that was reviewed.',
    'Model': 'A registered model configuration mapped to a dataset; historical selections remain distinct from current mappings.'}


class Connection(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    catalog_id: str = Field(pattern=r'^ocid1\.datacatalog\.[a-z0-9.\-]+$', max_length=255)
    region: str = Field(pattern=r'^[a-z]{2}-[a-z]+-\d+$', max_length=60)


class PublishInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset_ids: list[str] = Field(min_length=1, max_length=100)


def read_config():
    try:
        return Connection(**core.store.json(CONFIG)).model_dump()
    except FileNotFoundError:
        return None
    except (ValueError, TypeError):
        raise HTTPException(503, 'Saved OCI catalog connection is invalid.') from None


def client(config):
    if os.getenv('AEGIS_LOCAL_ONLY') == 'true':
        raise HTTPException(409, 'Local-only mode blocks OCI catalog connections and publication.')
    from .storage_config import active
    from .oci_adapters import _client
    storage = active()
    return _client('data_catalog', region=config['region'], auth_mode=storage.get('oci_storage_auth_mode'),
                   profile=storage.get('oci_storage_profile'), config_file=storage.get('oci_storage_config_file'),
                   key_file=storage.get('oci_storage_key_file'))


def items(response):
    data = response.data
    return data if isinstance(data, list) else data.items


def all_items(operation, *args, **kwargs):
    result, page = [], None
    while True:
        response = operation(*args, **kwargs, **({'page': page} if page else {}))
        result.extend(items(response))
        page = response.headers.get('opc-next-page')
        if not page:
            return result


def upsert_glossary(client, catalog_id, dataset, models):
    # Stable IDs prevent a dataset rename from creating another glossary.
    name = 'Aegis-' + dataset['id']
    existing = all_items(client.list_glossaries, catalog_id, display_name=name)
    policy = dataset['policy']
    description = json.dumps({'dataset': dataset['name'], 'dataset_id': dataset['id'],
                              'policy': {key: value for key, value in policy.items() if key != 'glossary'},
                              'metadata_counts': dataset['counts'], 'snapshot_only': True}, ensure_ascii=False)
    if existing:
        current_glossary = client.get_glossary(catalog_id, existing[0].key)
        glossary = client.update_glossary(catalog_id, existing[0].key,
            models.UpdateGlossaryDetails(display_name=name, description=description),
            if_match=current_glossary.headers['etag']).data
    else:
        glossary = client.create_glossary(catalog_id,
            models.CreateGlossaryDetails(display_name=name, description=description)).data
    listed = all_items(client.list_terms, catalog_id, glossary.key)
    category = next((term for term in listed if term.display_name == 'Aegis business terms' and not term.parent_term_key), None)
    if not category:
        category = client.create_term(catalog_id, glossary.key, models.CreateTermDetails(
            display_name='Aegis business terms', description='Definitions managed by Aegis metadata governance.',
            is_allowed_to_have_child_terms=True)).data
    existing_terms = {term.display_name: term for term in listed if term.parent_term_key == category.key}
    for term in policy['glossary']:
        if term['name'] in existing_terms:
            current_term = client.get_term(catalog_id, glossary.key, existing_terms[term['name']].key)
            client.update_term(catalog_id, glossary.key, current_term.data.key,
                               models.UpdateTermDetails(display_name=term['name'], description=term['definition'],
                                   parent_term_key=category.key),
                               if_match=current_term.headers['etag'])
        else:
            client.create_term(catalog_id, glossary.key,
                               models.CreateTermDetails(display_name=term['name'], description=term['definition'],
                                   parent_term_key=category.key, is_allowed_to_have_child_terms=False))
    # Previously published terms remain as history, explicitly marked retired.
    current = {term['name'] for term in policy['glossary']}
    for name, term in existing_terms.items():
        if name not in current:
            saved = client.get_term(catalog_id, glossary.key, term.key)
            if not (saved.data.description or '').startswith('Retired from the current Aegis glossary.'):
                client.update_term(catalog_id, glossary.key, term.key,
                                   models.UpdateTermDetails(display_name=name, description='Retired from the current Aegis glossary. ' + (saved.data.description or '')[:1800],
                                       parent_term_key=category.key),
                                   if_match=saved.headers['etag'])
    return glossary.key


def lineage_events(snapshot):
    """Publish actual saved source/result lineage, never extracted values or credentials."""
    nodes = {node['id']: node for node in snapshot['records']}
    generated = datetime.fromtimestamp(snapshot['generated_at'], timezone.utc).isoformat()
    producer = 'https://github.com/Maniatramco/Aegis'
    for node in nodes.values():
        if node['type'] not in ('Extraction', 'Review') or node['status'] not in ('ready', 'reviewed', 'completed'):
            continue
        inputs = []
        for edge in snapshot['relationships']:
            if edge['target'] == node['id'] and nodes[edge['source']]['type'] in ('Document', 'Extraction'):
                source = nodes[edge['source']]
                inputs.append({'namespace': 'aegis', 'name': source['id'], 'facets': {}})
        if not inputs:
            continue
        yield {'eventTime': generated, 'eventType': 'COMPLETE', 'producer': producer,
               'schemaURL': 'https://openlineage.io/spec/1-0-5/OpenLineage.json',
               'run': {'runId': str(uuid.uuid5(uuid.NAMESPACE_URL, node['id'] + ':' + str(node.get('version')))), 'facets': {}},
               'job': {'namespace': 'aegis', 'name': node['id'], 'facets': {}},
               'inputs': inputs, 'outputs': [{'namespace': 'aegis', 'name': node['id'], 'facets': {}}]}


def publish(snapshot, sdk_client, catalog_id):
    from .oci_adapters import _sdk
    models = _sdk().data_catalog.models
    platform = {'id': 'Platform-Glossary', 'name': 'Aegis metadata concepts', 'counts': {},
                'policy': {'glossary': [{'name': name, 'definition': definition} for name, definition in CONCEPTS.items()]}}
    upsert_glossary(sdk_client, catalog_id, platform, models)
    glossaries = [upsert_glossary(sdk_client, catalog_id, dataset, models) for dataset in snapshot['datasets']]
    # Mumbai rejected Custom Lineage Provider creation during the live pilot.
    # Keep verified glossary publication usable and never claim OCI ingestion.
    return {'glossaries': len(glossaries), 'platform_terms': len(CONCEPTS),
            'lineage_submitted': 0, 'lineage_status': 'available_in_aegis_and_export',
            'lineage_note': 'Inspect saved lineage in Aegis Metadata Relationships or export OpenLineage. Native OCI lineage ingestion is not enabled.'}


def install(app, auth):
    @app.get('/api/governance/oci')
    def status(actor=Depends(auth)):
        governance.require_manager(actor)
        config = read_config()
        try:
            saved = core.store.json(STATE)
        except FileNotFoundError:
            saved = None
        return {'configured': bool(config), 'connection': config, 'last_publication': saved,
                'access_note': 'OCI catalog access follows OCI IAM. Aegis dataset grants are not copied to OCI.'}

    @app.put('/api/governance/oci')
    def connect(body: Connection, actor=Depends(auth)):
        governance.require_manager(actor)
        try:
            catalog = client(body.model_dump()).get_catalog(body.catalog_id).data
            if catalog.lifecycle_state != 'ACTIVE':
                raise HTTPException(409, 'OCI catalog is not active.')
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(502, 'Could not verify OCI catalog. Check server-side OCI credentials, region and IAM access.') from None
        governance.require_manager(actor)
        core.store.put_json(CONFIG, body.model_dump())
        return status(actor)

    @app.post('/api/governance/oci/publish')
    def publish_metadata(body: PublishInput, actor=Depends(auth)):
        governance.require_manager(actor)
        config = read_config()
        if not config:
            raise HTTPException(409, 'Connect an active OCI catalog first.')
        with core.document_lock('workspace-reset'), core.document_lock('governance-oci-publish'):
            snapshot = governance.inventory(actor, body.dataset_ids)
            governance.require_manager(actor)
            governance.scope(actor, body.dataset_ids)
            try:
                result = publish(snapshot, client(config), config['catalog_id'])
            except HTTPException:
                raise
            except Exception:
                # A partially accepted OCI publication must never be reported as success.
                core.store.put_json(STATE, {'status': 'failed_or_partial', 'at': time.time()})
                raise HTTPException(502, 'OCI publication failed or was only partially accepted. Refresh OCI before retrying; Aegis policies are preserved.') from None
            saved = {'status': 'metadata_published', 'at': time.time(), 'dataset_ids': snapshot['dataset_ids'], **result}
            core.store.put_json(STATE, saved)
            governance.require_manager(actor)
            governance.scope(actor, body.dataset_ids)
            return saved
