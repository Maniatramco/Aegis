"""Publish a reviewed, metadata-only Aegis workflow schema snapshot to an existing OCI catalog.

No database connection, password, IAM change, DDL or harvesting job is created.
Snapshots must come from read-only inspection of the actual destination. This
operator tool is separate from the image-only application release workflow.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

TABLES = {'DATASET_TBL', 'DOCUMENT_TBL', 'PROMPT_TBL', 'EXTRACT_TBL', 'REVIEW_TBL',
          'MODEL_CONFIG_TBL', 'DATASET_MODEL_TBL', 'USER_DATASET_TBL'}


def validate(snapshot):
    if set(snapshot) != {'owner', 'tables', 'captured_at', 'source'}:
        raise ValueError('Schema snapshot must contain metadata only.')
    if not isinstance(snapshot['owner'], str) or not snapshot['owner'].isalnum():
        raise ValueError('Invalid schema owner.')
    seen = set()
    for table in snapshot['tables']:
        if set(table) != {'name', 'columns', 'primary_key', 'foreign_keys'} or table['name'] not in TABLES:
            raise ValueError('Only the eight Aegis workflow tables may be published.')
        if table['name'] in seen:
            raise ValueError('Duplicate table in schema snapshot.')
        seen.add(table['name'])
        for column in table['columns']:
            if set(column) != {'name', 'data_type', 'nullable', 'position'}:
                raise ValueError('Columns must contain definitions only, never table values.')
            if not isinstance(column['nullable'], bool) or not isinstance(column['position'], int):
                raise ValueError('Invalid column definition.')
        for foreign in table['foreign_keys']:
            if set(foreign) != {'columns', 'table', 'references'}:
                raise ValueError('Foreign keys must contain identifiers only.')
    if seen != TABLES:
        raise ValueError('The snapshot must cover all eight workflow tables.')
    return snapshot


def all_items(operation, *args, **kwargs):
    result, page = [], None
    while True:
        response = operation(*args, **kwargs, **({'page': page} if page else {}))
        result.extend(response.data if isinstance(response.data, list) else response.data.items)
        page = response.headers.get('opc-next-page')
        if not page:
            return result


def publish(client, models, catalog_id, source, snapshot):
    validate(snapshot)
    if set(source) != {'host', 'port', 'database'}:
        raise ValueError('Source may contain host, port and service metadata only; no credentials.')
    types = all_items(client.list_types, catalog_id)
    asset_type = next(t for t in types if t.name == 'Oracle Database' and t.type_category == 'dataAsset')
    folder_type = next(t for t in types if t.name == 'Oracle Schema' and t.type_category == 'folder')
    table_type = next(t for t in types if t.name == 'Table' and t.parent_type_key == folder_type.key)
    column_type = next(t for t in types if t.name == 'Primitive' and t.parent_type_key == table_type.key)
    found = all_items(client.list_data_assets, catalog_id, display_name='Aegis-Application-Metadata')
    if len(found) > 1:
        raise ValueError('Select an unambiguous managed data asset before publication.')
    asset = found[0] if found else client.create_data_asset(catalog_id, models.CreateDataAssetDetails(
        display_name='Aegis-Application-Metadata', type_key=asset_type.key, properties={'default': source},
        description='Aegis workflow schema metadata. No database credentials or harvesting connection are registered.')).data
    current = client.get_data_asset(catalog_id, asset.key).data
    if any(current.properties.get('default', {}).get(key) != value for key, value in source.items()):
        raise ValueError('Existing data asset identifies a different source; nothing was overwritten.')
    timestamp = datetime.fromtimestamp(snapshot['captured_at'], timezone.utc)
    folders = all_items(client.list_folders, catalog_id, asset.key, display_name=snapshot['owner'])
    if len(folders) > 1:
        raise ValueError('Ambiguous schema folder.')
    folder = folders[0] if folders else client.create_folder(catalog_id, asset.key, models.CreateFolderDetails(
        display_name=snapshot['owner'], type_key=folder_type.key, time_external=timestamp,
        description='Read-only snapshot of Aegis workflow schema definitions; no table rows.')).data
    columns = 0
    for table in snapshot['tables']:
        definition = json.dumps({'primary_key': table['primary_key'], 'foreign_keys': table['foreign_keys'],
                                 'captured_at': snapshot['captured_at'], 'snapshot_only': True})
        matches = [entity for entity in all_items(client.list_entities, catalog_id, asset.key, display_name=table['name'])
                   if entity.folder_key == folder.key]
        if len(matches) > 1:
            raise ValueError('Ambiguous workflow table metadata.')
        if matches:
            old = client.get_entity(catalog_id, asset.key, matches[0].key)
            entity = client.update_entity(catalog_id, asset.key, old.data.key, models.UpdateEntityDetails(
                display_name=table['name'], folder_key=folder.key, time_external=timestamp, description=definition),
                if_match=old.headers['etag']).data
        else:
            entity = client.create_entity(catalog_id, asset.key, models.CreateEntityDetails(
                display_name=table['name'], type_key=table_type.key, folder_key=folder.key,
                time_external=timestamp, description=definition)).data
        existing = {attr.display_name: attr for attr in all_items(client.list_attributes, catalog_id, asset.key, entity.key)}
        for column in table['columns']:
            values = dict(display_name=column['name'], external_data_type=column['data_type'],
                          is_nullable=column['nullable'], position=column['position'], time_external=timestamp,
                          description='Primary key column.' if column['name'] in table['primary_key'] else 'Aegis workflow column definition; no data values.')
            if column['name'] in existing:
                old = client.get_attribute(catalog_id, asset.key, entity.key, existing[column['name']].key)
                client.update_attribute(catalog_id, asset.key, entity.key, old.data.key,
                                        models.UpdateAttributeDetails(**values), if_match=old.headers['etag'])
            else:
                client.create_attribute(catalog_id, asset.key, entity.key,
                                        models.CreateAttributeDetails(type_key=column_type.key, **values))
            columns += 1
    return {'data_asset_key': asset.key, 'schema_folder_key': folder.key,
            'tables_published': len(snapshot['tables']), 'columns_published': columns,
            'source_captured_at': snapshot['captured_at'], 'rows_read': 0,
            'database_connection_registered': False, 'harvesting_enabled': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog-id', required=True)
    parser.add_argument('--source', type=Path, required=True, help='Private JSON with host, port and database service only')
    parser.add_argument('--schema', type=Path, required=True, help='Reviewed live schema metadata snapshot')
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--profile', default='DEFAULT')
    parser.add_argument('--publish', action='store_true', help='Explicitly publish metadata; otherwise only validate locally')
    args = parser.parse_args()
    snapshot = validate(json.loads(args.schema.read_text(encoding='utf-8-sig')))
    source = json.loads(args.source.read_text(encoding='utf-8-sig'))
    if not args.publish:
        print(json.dumps({'schema_validated': True, 'tables': len(snapshot['tables']), 'publication': 'not attempted'}))
        return
    import oci
    client = oci.data_catalog.DataCatalogClient(oci.config.from_file(profile_name=args.profile),
        timeout=(10, 35), retry_strategy=oci.retry.NoneRetryStrategy())
    try:
        result = publish(client, oci.data_catalog.models, args.catalog_id, source, snapshot)
    except Exception:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps({'status': 'failed_or_partial'}), encoding='utf-8')
        raise SystemExit('Schema publication failed or was partial. Inspect OCI and the reviewed snapshot before retrying.') from None
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps({'status': 'published', **result}, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
