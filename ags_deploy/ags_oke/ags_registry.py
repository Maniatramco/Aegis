"""Publish only approved ARM64 component images to private OCI repositories.

Credentials stay in ignored local runtime files and are supplied on stdin.
Use --push to publish; without it, only image/storage checks are performed.
"""
import argparse
import base64
import json
import os
import subprocess
from pathlib import Path

import oci

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / 'ags_runtime/ags_oke'
REGISTRY = 'bom.ocir.io'
NAMESPACE = 'bmyljaecivrj'
IMAGES = {'web': 'aegis-oke-web:7c200d7-arm64', 'backend': 'aegis-oke-backend:7c200d7-arm64',
    'ssh': 'aegis-oke-ssh:pilot-arm64'}


def command(argv, **kwargs):
    return subprocess.run(argv, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--push', action='store_true')
    args = parser.parse_args()
    cfg = oci.config.from_file()
    if cfg['region'] != 'ap-mumbai-1':
        raise ValueError('Only Mumbai is approved')
    kw = dict(timeout=(10, 30), retry_strategy=oci.retry.NoneRetryStrategy())
    artifacts = oci.artifacts.ArtifactsClient(cfg, **kw)
    repos = oci.pagination.list_call_get_all_results(artifacts.list_container_repositories, cfg['tenancy']).data
    repos = getattr(repos, 'items', repos)
    if any(not x.display_name.startswith('ags-aegis-') for x in repos):
        raise ValueError('Existing registry use needs a combined free-storage review')
    inspect = json.loads(subprocess.check_output(['docker', 'image', 'inspect', *IMAGES.values()]))
    if any(x['Architecture'] != 'arm64' for x in inspect):
        raise ValueError('Every application image must be ARM64')
    total = sum(x['Size'] for x in inspect)
    # Conservative: two complete uncompressed releases plus current bucket use.
    bucket = oci.object_storage.ObjectStorageClient(cfg, **kw).get_bucket(NAMESPACE, 'mk-aegis',
        fields=['approximateSize']).data
    if 2 * total + bucket.approximate_size > 6_000_000_000:
        raise ValueError('Image storage exceeds the reserved conservative free-storage budget')
    print('ARM64 images checked; active plus rollback storage reservation fits below 6 GB', flush=True)
    if not args.push:
        return
    identity = oci.identity.IdentityClient(cfg, **kw)
    user = identity.get_user(cfg['user']).data
    username = NAMESPACE + '/' + user.name
    secret_path = RUNTIME / 'secrets/ocir-token.json'
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    if not secret_path.exists():
        existing = identity.list_auth_tokens(cfg['user']).data
        if any(x.description == 'ags-aegis-oke-registry' for x in existing):
            raise RuntimeError('Registry token exists but is not saved locally; recover it before creating another')
        response = identity.create_auth_token(user_id=cfg['user'],
            create_auth_token_details=oci.identity.models.CreateAuthTokenDetails(description='ags-aegis-oke-registry'))
        secret_path.write_text(json.dumps({'id': response.data.id, 'token': response.data.token,
            'username': username}), encoding='utf-8')
        print('Dedicated registry token created and saved outside Git; value not displayed', flush=True)
    auth = json.loads(secret_path.read_text(encoding='utf-8'))
    env = os.environ.copy()
    env['DOCKER_CONFIG'] = str(RUNTIME / 'docker-config')
    Path(env['DOCKER_CONFIG']).mkdir(parents=True, exist_ok=True)
    docker_config = Path(env['DOCKER_CONFIG']) / 'config.json'
    logged_in = docker_config.exists() and REGISTRY in json.loads(docker_config.read_text()).get('auths', {})
    if not logged_in:
        command(['docker', 'login', REGISTRY, '--username', auth['username'], '--password-stdin'],
            input=(auth['token'] + '\n').encode(), env=env)
    release_file = RUNTIME / 'release.json'
    release = json.loads(release_file.read_text()) if release_file.exists() else {}
    known = {x.display_name: x for x in repos}
    for component, local in IMAGES.items():
        name = 'ags-aegis-' + component
        if name not in known:
            response = artifacts.create_container_repository(oci.artifacts.models.CreateContainerRepositoryDetails(
                compartment_id=cfg['tenancy'], display_name=name, is_public=False,
                freeform_tags={'application': 'Aegis', 'deployment': 'ags-oke-free-pilot'}))
            print('Private repository created; deployment images will be pinned by digest:', name, flush=True)
        else:
            if known[name].is_public:
                raise ValueError('Repository must be private')
        remote = f'{REGISTRY}/{NAMESPACE}/{name}:7c200d7-arm64'
        command(['docker', 'tag', local, remote], env=env)
        command(['docker', 'push', remote], env=env)
        image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', remote], env=env))[0]
        digest = next(x for x in image['RepoDigests'] if x.startswith(f'{REGISTRY}/{NAMESPACE}/{name}@'))
        release[component + '_image'] = digest
        release_file.write_text(json.dumps(release, indent=2), encoding='utf-8')
        print('Published immutable component:', component, digest, flush=True)
    auth_string = base64.b64encode((auth['username'] + ':' + auth['token']).encode()).decode()
    pull_secret = {'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': 'ocir-pull', 'namespace': 'aegis-oci'},
        'type': 'kubernetes.io/dockerconfigjson', 'data': {'.dockerconfigjson': base64.b64encode(json.dumps(
            {'auths': {REGISTRY: {'auth': auth_string}}}).encode()).decode()}}
    (RUNTIME / 'secrets/ocir-pull.json').write_text(json.dumps(pull_secret), encoding='utf-8')


if __name__ == '__main__':
    main()
