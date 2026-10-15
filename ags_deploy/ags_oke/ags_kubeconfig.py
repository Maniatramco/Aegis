"""Use the installed OCI SDK for OKE kubectl authentication, without CLI upgrades.

The token format follows Oracle's UPL/Apache-licensed OCI CLI generate-token:
https://github.com/oracle/oci-cli/blob/master/services/container_engine/src/
oci_cli_container_engine/containerengine_cli_extended.py
Tokens go directly to kubectl's exec plugin; never write them to the runbook.
"""
import argparse
import base64
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import oci
import yaml
from oci._vendor.requests import Request

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / 'ags_runtime' / 'ags_oke'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--token', action='store_true')
    args = parser.parse_args()
    state = json.loads((RUNTIME / 'provision-state.json').read_text(encoding='utf-8'))
    cfg = oci.config.from_file()
    if cfg['region'] != state['region']:
        raise ValueError('OCI profile region does not match this deployment')
    ce = oci.container_engine.ContainerEngineClient(cfg, timeout=(10, 30),
        retry_strategy=oci.retry.NoneRetryStrategy())
    cluster = state['cluster']
    if args.token:
        url = f'https://containerengine.{cfg["region"]}.oraclecloud.com/cluster_request/{cluster}'
        signed = ce.base_client.signer.do_request_sign(Request('GET', url).prepare())
        request = Request('GET', url, params={
            'authorization': signed.headers['authorization'], 'date': signed.headers['date']}).prepare()
        print(json.dumps({'apiVersion': 'client.authentication.k8s.io/v1beta1',
            'kind': 'ExecCredential', 'status': {
                'token': base64.urlsafe_b64encode(request.url.encode()).decode(),
                'expirationTimestamp': (datetime.now(timezone.utc) + timedelta(minutes=4)).isoformat().replace('+00:00', 'Z')}}))
        return
    info = ce.get_cluster(cluster).data
    if info.lifecycle_state != 'ACTIVE' or info.type != 'BASIC_CLUSTER':
        raise ValueError('The approved Basic cluster is not active')
    response = ce.create_kubeconfig(cluster, create_cluster_kubeconfig_content_details=
        oci.container_engine.models.CreateClusterKubeconfigContentDetails(token_version='2.0.0', endpoint='PUBLIC_ENDPOINT'))
    config = yaml.safe_load(response.data.content)
    for user in config['users']:
        user['user'] = {'exec': {'apiVersion': 'client.authentication.k8s.io/v1beta1',
            'command': str(Path(sys.executable).resolve()),
            'args': [str(Path(__file__).resolve()), '--token'], 'interactiveMode': 'Never'}}
    output = RUNTIME / 'kubeconfig.yaml'
    output.write_text(yaml.safe_dump(config), encoding='utf-8')
    print(f'Kubeconfig saved outside Git: {output}')


if __name__ == '__main__':
    main()
