"""Read-only cloud document adapters. Locations are scoped server-side, never arbitrary URLs."""
import io
import ipaddress
import json
import re
import socket
from urllib.parse import quote, urlparse

import httpx

FORMATS = {'pdf', 'docx', 'txt', 'json'}
GOOGLE_EXPORTS = {
    'application/vnd.google-apps.document': ('application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.docx'),
    'application/vnd.google-apps.spreadsheet': ('application/pdf', '.pdf'),
    'application/vnd.google-apps.presentation': ('application/pdf', '.pdf'),
}
FOLDER = 'application/vnd.google-apps.folder'


class SourceError(ValueError):
    pass


def supported(name):
    return name.rsplit('.', 1)[-1].lower() in FORMATS


def segment(value):
    return quote(value, safe='')


def checked_response(response):
    if response.status_code in (401, 403):
        raise SourceError('Cloud authentication or read permission was denied. Check the saved credentials and location access.')
    if response.status_code == 404:
        raise SourceError('Cloud file or location is unavailable, or access was removed.')
    if response.status_code == 429:
        raise SourceError('The cloud provider is throttling requests. Wait and retry.')
    if response.status_code >= 400:
        raise SourceError('Cloud request failed. Check the location and provider availability, then retry.')
    return response


def request_json(method, url, **kwargs):
    with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as client:
        response = checked_response(client.request(method, url, **kwargs))
        if response.status_code >= 300:
            raise SourceError('Unexpected cloud API redirect.')
        return response.json()


def download(url, headers, limit, microsoft_redirect=False):
    # Graph returns a short-lived preauthenticated SharePoint URL. Never forward
    # its Graph bearer token to that host or accept a user-supplied destination.
    with httpx.Client(timeout=60, follow_redirects=False, trust_env=False) as client:
        for _ in range(4):
            with client.stream('GET', url, headers=headers) as response:
                checked_response(response)
                if response.status_code in (301, 302, 303, 307, 308) and microsoft_redirect:
                    url = response.headers.get('location', '')
                    parsed = urlparse(url)
                    host = parsed.hostname or ''
                    if parsed.scheme != 'https' or parsed.port not in (None, 443) or parsed.username or parsed.password or not any(host.endswith(suffix) for suffix in ('.sharepoint.com', '.sharepointonline.com', '.1drv.com')):
                        raise SourceError('Unexpected Microsoft download destination.')
                    addresses = socket.getaddrinfo(host, 443)
                    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
                        raise SourceError('Microsoft download destination is not public.')
                    headers = {}
                    continue
                if response.status_code >= 300:
                    raise SourceError('Unexpected cloud download redirect.')
                if int(response.headers.get('content-length', '0')) > limit:
                    raise SourceError('File exceeds the configured upload size limit.')
                output = io.BytesIO()
                for block in response.iter_bytes(64 * 1024):
                    if output.tell() + len(block) > limit:
                        raise SourceError('File exceeds the configured upload size limit.')
                    output.write(block)
                raw = output.getvalue()
                if not raw:
                    raise SourceError('The cloud file is empty.')
                return raw
    raise SourceError('Too many Microsoft download redirects.')


class S3:
    def __init__(self, cfg, credentials):
        import boto3
        from botocore.config import Config
        auth = {}
        if cfg['auth_mode'] == 'access_key':
            auth = {'aws_access_key_id': credentials['access_key_id'], 'aws_secret_access_key': credentials['secret_access_key']}
            if credentials.get('session_token'):
                auth['aws_session_token'] = credentials['session_token']
        self.client = boto3.client('s3', region_name=cfg['region'], config=Config(connect_timeout=10, read_timeout=60, retries={'max_attempts': 2, 'mode': 'standard'}), **auth)
        self.cfg = cfg

    def args(self):
        return {'Bucket': self.cfg['bucket'], **({'ExpectedBucketOwner': self.cfg['expected_owner']} if self.cfg.get('expected_owner') else {})}

    def scope(self, key):
        prefix = self.cfg.get('prefix', '')
        if not key.startswith(prefix):
            raise SourceError('Object is outside the configured S3 prefix.')

    def browse(self, folder='', cursor=''):
        folder = folder or self.cfg.get('prefix', '')
        self.scope(folder)
        if folder and not folder.endswith('/'):
            raise SourceError('Choose a folder prefix ending in /.')
        response = self.client.list_objects_v2(**self.args(), Prefix=folder, Delimiter='/', MaxKeys=100, **({'ContinuationToken': cursor} if cursor else {}))
        items = [{'id': p['Prefix'], 'name': p['Prefix'][len(folder):].rstrip('/'), 'folder': True} for p in response.get('CommonPrefixes', [])]
        for value in response.get('Contents', []):
            if value['Key'] == folder or value['Key'].endswith('/'):
                continue
            name = value['Key'].rsplit('/', 1)[-1]
            items.append({'id': value['Key'], 'name': name, 'folder': False, 'supported': supported(name), 'size': value['Size'], 'revision': value.get('ETag', ''), 'modified': str(value.get('LastModified', ''))})
        return items, response.get('NextContinuationToken', '')

    def fetch(self, item, limit):
        self.scope(item['id'])
        response = self.client.get_object(**self.args(), Key=item['id'], **({'IfMatch': item['revision']} if item.get('revision') else {}))
        body = response['Body']
        try:
            if response.get('ContentLength', 0) > limit:
                raise SourceError('File exceeds the configured upload size limit.')
            raw = body.read(limit + 1)
            if len(raw) > limit or not raw:
                raise SourceError('Cloud file is empty or exceeds the upload size limit.')
        finally:
            body.close()
        return item['name'], raw, {'remote_id': item['id'], 'revision': response.get('VersionId') or response.get('ETag', ''), 'original_url': 's3://' + self.cfg['bucket'] + '/' + item['id']}


class SharePoint:
    BASE = 'https://graph.microsoft.com/v1.0'

    def __init__(self, cfg, credentials):
        self.cfg = cfg
        data = request_json('POST', 'https://login.microsoftonline.com/' + cfg['tenant_id'] + '/oauth2/v2.0/token', data={'client_id': cfg['client_id'], 'client_secret': credentials['client_secret'], 'scope': 'https://graph.microsoft.com/.default', 'grant_type': 'client_credentials'})
        self.headers = {'Authorization': 'Bearer ' + data['access_token']}
        # Bind the drive to the selected site, even with broader app grants.
        path = '/sites/' + segment(cfg['site_id']) + '/drives'
        page = self.get(path, **{'$select': 'id', '$top': 100})
        found = any(d.get('id') == cfg['drive_id'] for d in page.get('value', []))
        for _ in range(100):
            next_page = page.get('@odata.nextLink', '')
            if found or not next_page:
                break
            parsed = urlparse(next_page)
            if parsed.scheme != 'https' or parsed.netloc != 'graph.microsoft.com' or parsed.path != '/v1.0' + path:
                raise SourceError('Invalid SharePoint library cursor.')
            page = request_json('GET', next_page, headers=self.headers)
            found = any(d.get('id') == cfg['drive_id'] for d in page.get('value', []))
        if not found:
            raise SourceError('The document library does not belong to the configured site.')

    def get(self, path, **params):
        return request_json('GET', self.BASE + path, headers=self.headers, params=params or None)

    def path(self, item):
        return '/drives/' + segment(self.cfg['drive_id']) + ('/root' if item == 'root' else '/items/' + segment(item))

    def scoped(self, item):
        root = self.cfg.get('folder_id') or 'root'
        root_id = self.get(self.path(root))['id']
        current = self.get(self.path(item))
        original = current
        for _ in range(64):
            if current['id'] == root_id:
                if original.get('remoteItem'):
                    raise SourceError('Remote shortcuts are not imported. Connect their original library instead.')
                return original
            parent = current.get('parentReference', {})
            if parent.get('driveId') != self.cfg['drive_id'] or not parent.get('id'):
                break
            current = self.get(self.path(parent['id']))
        raise SourceError('Item is outside the configured SharePoint folder.')

    def browse(self, folder='', cursor=''):
        folder = folder or self.cfg.get('folder_id') or 'root'
        info = self.scoped(folder)
        if 'folder' not in info:
            raise SourceError('Choose a SharePoint folder.')
        path = self.path(folder) + '/children'
        params = {'$top': 100, '$select': 'id,name,size,eTag,lastModifiedDateTime,folder,file,remoteItem,webUrl'}
        if cursor:
            parsed = urlparse(cursor)
            if parsed.scheme != 'https' or parsed.netloc != 'graph.microsoft.com' or parsed.path != '/v1.0' + path:
                raise SourceError('Invalid SharePoint page cursor.')
            response = request_json('GET', cursor, headers=self.headers)
        else:
            response = self.get(path, **params)
        items = [{'id': v['id'], 'name': v['name'], 'folder': 'folder' in v, 'supported': 'file' in v and not v.get('remoteItem') and supported(v['name']), 'size': v.get('size', 0), 'revision': v.get('eTag', ''), 'modified': v.get('lastModifiedDateTime', '')} for v in response.get('value', [])]
        return items, response.get('@odata.nextLink', '')

    def fetch(self, item, limit):
        info = self.scoped(item['id'])
        if 'file' not in info or not supported(info['name']):
            raise SourceError('Select a supported SharePoint file.')
        if info.get('eTag') != item.get('revision'):
            raise SourceError('The cloud file changed. Refresh the file list and select it again.')
        raw = download(self.BASE + self.path(item['id']) + '/content', self.headers | {'If-Match': info['eTag']}, limit, microsoft_redirect=True)
        if self.scoped(item['id']).get('eTag') != info.get('eTag'):
            raise SourceError('The cloud file changed during download. Refresh and retry.')
        return info['name'], raw, {'remote_id': item['id'], 'revision': info.get('eTag', ''), 'original_url': info.get('webUrl', '')}


class GoogleDrive:
    BASE = 'https://www.googleapis.com/drive/v3/files'
    FIELDS = 'id,name,mimeType,size,modifiedTime,version,parents,trashed,webViewLink,capabilities(canDownload)'

    def __init__(self, cfg, credentials):
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
        info = json.loads(credentials['service_account'])
        # Do not let uploaded JSON send signed assertions to arbitrary hosts.
        info['token_uri'] = 'https://oauth2.googleapis.com/token'
        identity = service_account.Credentials.from_service_account_info(info, scopes=['https://www.googleapis.com/auth/drive.readonly'])
        identity.refresh(Request())
        self.headers = {'Authorization': 'Bearer ' + identity.token}
        self.cfg = cfg

    def get(self, item):
        return request_json('GET', self.BASE + '/' + segment(item), headers=self.headers, params={'fields': self.FIELDS, 'supportsAllDrives': 'true'})

    def scoped(self, item):
        current = self.get(item)
        original = current
        for _ in range(64):
            if current.get('trashed'):
                raise SourceError('Cloud item is in the trash.')
            if current['id'] == self.cfg['folder_id']:
                return original
            parents = current.get('parents', [])
            if len(parents) != 1:
                break
            current = self.get(parents[0])
        raise SourceError('Item is outside the configured Google Drive folder.')

    def browse(self, folder='', cursor=''):
        folder = folder or self.cfg['folder_id']
        if self.scoped(folder)['mimeType'] != FOLDER:
            raise SourceError('Choose a Google Drive folder.')
        # IDs are validated as opaque IDs before entering the Drive query.
        if not re.fullmatch(r'[A-Za-z0-9_-]+', folder):
            raise SourceError('Invalid Drive folder identifier.')
        params = {'q': "'" + folder + "' in parents and trashed = false", 'pageSize': 100, 'fields': 'nextPageToken,files(' + self.FIELDS + ')', 'supportsAllDrives': 'true', 'includeItemsFromAllDrives': 'true'}
        if cursor:
            params['pageToken'] = cursor
        response = request_json('GET', self.BASE, headers=self.headers, params=params)
        items = []
        for v in response.get('files', []):
            export = GOOGLE_EXPORTS.get(v['mimeType'])
            name = v['name'] + (export[1] if export and not v['name'].lower().endswith(export[1]) else '')
            items.append({'id': v['id'], 'name': name, 'folder': v['mimeType'] == FOLDER, 'supported': (bool(export) or supported(name)) and v.get('capabilities', {}).get('canDownload', True) and v['mimeType'] != 'application/vnd.google-apps.shortcut', 'size': int(v.get('size', 0)), 'revision': str(v.get('version', '')) + ':' + v.get('modifiedTime', ''), 'modified': v.get('modifiedTime', '')})
        return items, response.get('nextPageToken', '')

    def fetch(self, item, limit):
        info = self.scoped(item['id'])
        revision = str(info.get('version', '')) + ':' + info.get('modifiedTime', '')
        if revision != item.get('revision'):
            raise SourceError('The cloud file changed. Refresh the file list and select it again.')
        if info.get('capabilities', {}).get('canDownload') is False:
            raise SourceError('Downloading this cloud file is not permitted.')
        export = GOOGLE_EXPORTS.get(info['mimeType'])
        url = self.BASE + '/' + segment(item['id'])
        if export:
            url += '/export?mimeType=' + quote(export[0], safe='')
        elif info['mimeType'].startswith('application/vnd.google-apps.'):
            raise SourceError('This Google file type cannot be imported.')
        else:
            url += '?alt=media&supportsAllDrives=true'
        raw = download(url, self.headers, limit)
        latest = self.scoped(item['id'])
        if str(latest.get('version', '')) + ':' + latest.get('modifiedTime', '') != revision:
            raise SourceError('The cloud file changed during download. Refresh and retry.')
        return item['name'], raw, {'remote_id': item['id'], 'revision': revision, 'original_url': 'https://drive.google.com/file/d/' + segment(item['id']) + '/view'}


def adapter(cfg, credentials):
    return {'s3': S3, 'sharepoint': SharePoint, 'google_drive': GoogleDrive}[cfg['provider']](cfg, credentials)
