"""Provision only the approved single-node Basic OKE configuration.

Without --create this performs read-only checks. State and request tokens are
kept outside Git so an interrupted request can be reconciled without duplicates.
No account upgrade, paid fallback, scaling, database change or app cutover occurs.
"""
import argparse
import ipaddress
import json
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

import oci

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / 'ags_runtime' / 'ags_oke' / 'provision-state.json'
REGION = 'ap-mumbai-1'
VERSION = 'v1.36.4'
TAGS = {'application': 'Aegis', 'deployment': 'ags-oke-free-pilot'}
NAME = 'ags-aegis-basic'
VCN_CIDR = '10.42.0.0/16'


def stamp():
    return datetime.now(timezone.utc).isoformat()


def save(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, indent=2), encoding='utf-8')
    temporary.replace(STATE)


def event(state, message, **details):
    state.setdefault('events', []).append({'time': stamp(), 'message': message, **details})
    save(state)
    print(message, json.dumps(details) if details else '', flush=True)


def token(state, key):
    value = state.setdefault('tokens', {}).setdefault(key, str(uuid.uuid4()))
    save(state)
    return value


def wait_request(ce, state, key):
    request = state['requests'][key]
    previous = None
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        work = ce.get_work_request(request).data
        if work.status != previous:
            event(state, f'{key} work request', status=work.status)
            previous = work.status
        for resource in work.resources:
            if resource.entity_type.lower().replace('_', '') == key.replace('_', ''):
                state[key] = resource.identifier
        save(state)
        if work.status == 'SUCCEEDED':
            return
        if work.status in ('FAILED', 'CANCELED', 'CANCELLED'):
            errors = oci.util.to_dict(ce.list_work_request_errors(request).data)
            event(state, f'{key} provisioning stopped', errors=errors)
            raise RuntimeError(f'{key} work request {work.status}; see recorded Oracle errors')
        time.sleep(10)
    raise TimeoutError(f'{key} is still provisioning; reconcile the saved work request before retrying')


def rules(source, ports):
    return [oci.core.models.IngressSecurityRule(
        protocol='6', source=source,
        tcp_options=oci.core.models.TcpOptions(
            destination_port_range=oci.core.models.PortRange(min=port, max=port)))
        for port in ports]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--create', action='store_true', help='Submit the actual approved OCI creation requests')
    args = parser.parse_args()
    cfg = oci.config.from_file()
    if cfg['region'] != REGION:
        raise ValueError('Only the approved Mumbai region is permitted')
    kwargs = dict(timeout=(10, 30), retry_strategy=oci.retry.NoneRetryStrategy())
    identity = oci.identity.IdentityClient(cfg, **kwargs)
    if identity.get_tenancy(cfg['tenancy']).data.home_region_key != 'BOM':
        raise ValueError('The approved region must be the tenancy home region')
    net = oci.core.VirtualNetworkClient(cfg, **kwargs)
    compute = oci.core.ComputeClient(cfg, **kwargs)
    block = oci.core.BlockstorageClient(cfg, **kwargs)
    ce = oci.container_engine.ContainerEngineClient(cfg, **kwargs)
    state = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {'region': REGION}
    if state.get('region') != REGION:
        raise ValueError('Saved deployment belongs to a different region')
    ad = identity.list_availability_domains(cfg['tenancy']).data[0].name
    instances = oci.pagination.list_call_get_all_results(compute.list_instances, cfg['tenancy']).data
    active = [x for x in instances if x.lifecycle_state != 'TERMINATED']
    unrelated = [x for x in active if x.freeform_tags.get('deployment') != TAGS['deployment']]
    if unrelated:
        raise ValueError('Existing compute consumption requires a new free-allowance review')
    volumes = oci.pagination.list_call_get_all_results(block.list_volumes, compartment_id=cfg['tenancy']).data
    boots = []
    for availability in identity.list_availability_domains(cfg['tenancy']).data:
        boots.extend(oci.pagination.list_call_get_all_results(block.list_boot_volumes,
            availability_domain=availability.name, compartment_id=cfg['tenancy']).data)
    total = sum(x.size_in_gbs for x in volumes + boots if x.lifecycle_state != 'TERMINATED')
    if total > (150 if state.get('node_pool') else 0):
        raise ValueError('Existing volume consumption requires a new free-allowance review')
    options = ce.get_node_pool_options('all', compartment_id=cfg['tenancy']).data
    if VERSION not in options.kubernetes_versions or 'VM.Standard.A1.Flex' not in options.shapes:
        raise ValueError('The approved node shape or Kubernetes version is unavailable; no substitute selected')
    sources = [x for x in options.sources if 'aarch64' in x.source_name.lower()
        and f'OKE-{VERSION[1:]}-' in x.source_name and 'Oracle-Linux-9.' in x.source_name]
    if not sources:
        raise ValueError('No compatible ARM64 managed-node image is available')
    source = sorted(sources, key=lambda x: x.source_name, reverse=True)[0]
    public_ip = str(ipaddress.IPv4Address(urllib.request.urlopen('https://api.ipify.org', timeout=10).read().decode()))
    state['management_cidr'] = state.get('management_cidr', public_ip + '/32')
    if state['management_cidr'] != public_ip + '/32':
        raise ValueError('Laptop public IP changed; review management rules before resuming')
    state['image'] = {'id': source.image_id, 'name': source.source_name}
    state['approved'] = {'cluster_type': 'BASIC_CLUSTER', 'version': VERSION,
        'shape': 'VM.Standard.A1.Flex', 'nodes': 1, 'ocpus': 2, 'memory_gb': 12,
        'boot_gb': 50, 'planned_total_volume_gb': 150, 'no_upgrade': True}
    event(state, 'Preflight passed', create_requested=args.create)
    if not args.create:
        return
    compartment = cfg['tenancy']
    state.setdefault('requests', {})
    if not state.get('vcn'):
        response = net.create_vcn(oci.core.models.CreateVcnDetails(
            compartment_id=compartment, cidr_block=VCN_CIDR, display_name='ags-aegis-vcn',
            dns_label='agsaegis', freeform_tags=TAGS), opc_retry_token=token(state, 'vcn'))
        state['vcn'] = response.data.id
        event(state, 'VCN created', id=state['vcn'], request_id=response.headers.get('opc-request-id'))
    if not state.get('internet_gateway'):
        response = net.create_internet_gateway(oci.core.models.CreateInternetGatewayDetails(
            compartment_id=compartment, vcn_id=state['vcn'], is_enabled=True,
            display_name='ags-aegis-ig', freeform_tags=TAGS), opc_retry_token=token(state, 'internet_gateway'))
        state['internet_gateway'] = response.data.id
        event(state, 'Internet Gateway created', id=response.data.id)
    if not state.get('route_table'):
        response = net.create_route_table(oci.core.models.CreateRouteTableDetails(
            compartment_id=compartment, vcn_id=state['vcn'], display_name='ags-aegis-public-routes',
            freeform_tags=TAGS, route_rules=[oci.core.models.RouteRule(destination='0.0.0.0/0',
                destination_type='CIDR_BLOCK', network_entity_id=state['internet_gateway'])]),
            opc_retry_token=token(state, 'route_table'))
        state['route_table'] = response.data.id
        event(state, 'Public route table created', id=response.data.id)
    egress = [oci.core.models.EgressSecurityRule(protocol='all', destination='0.0.0.0/0')]
    ingress = {
        'api': rules('10.42.1.0/24', [6443, 12250]) + rules(state['management_cidr'], [6443]),
        'worker': [oci.core.models.IngressSecurityRule(protocol='all', source='10.42.1.0/24'),
            oci.core.models.IngressSecurityRule(protocol='all', source='10.42.0.0/24'),
            oci.core.models.IngressSecurityRule(protocol='all', source='10.42.2.0/24')]
            + rules(state['management_cidr'], [22, 32022]),
        'lb': rules('0.0.0.0/0', [80, 443]),
    }
    for index, role in enumerate(('api', 'worker', 'lb')):
        key = f'{role}_security_list'
        if not state.get(key):
            response = net.create_security_list(oci.core.models.CreateSecurityListDetails(
                compartment_id=compartment, vcn_id=state['vcn'], display_name=f'ags-aegis-{role}-security',
                freeform_tags=TAGS, ingress_security_rules=ingress[role], egress_security_rules=egress),
                opc_retry_token=token(state, key))
            state[key] = response.data.id
            event(state, f'{role} security list created', id=response.data.id)
        key = f'{role}_subnet'
        if not state.get(key):
            response = net.create_subnet(oci.core.models.CreateSubnetDetails(
                compartment_id=compartment, vcn_id=state['vcn'], display_name=f'ags-aegis-{role}-subnet',
                cidr_block=f'10.42.{index}.0/24', dns_label=role, freeform_tags=TAGS,
                route_table_id=state['route_table'], security_list_ids=[state[f'{role}_security_list']],
                prohibit_public_ip_on_vnic=False), opc_retry_token=token(state, key))
            state[key] = response.data.id
            event(state, f'{role} subnet created', id=response.data.id)
    if not state.get('cluster') and not state['requests'].get('cluster'):
        response = ce.create_cluster(oci.container_engine.models.CreateClusterDetails(
            compartment_id=compartment, name=NAME, vcn_id=state['vcn'], kubernetes_version=VERSION,
            type='BASIC_CLUSTER', freeform_tags=TAGS,
            endpoint_config=oci.container_engine.models.CreateClusterEndpointConfigDetails(
                subnet_id=state['api_subnet'], is_public_ip_enabled=True),
            cluster_pod_network_options=[oci.container_engine.models.FlannelOverlayClusterPodNetworkOptionDetails()],
            options=oci.container_engine.models.ClusterCreateOptions(service_lb_subnet_ids=[state['lb_subnet']],
                kubernetes_network_config=oci.container_engine.models.KubernetesNetworkConfig(
                    pods_cidr='10.244.0.0/16', services_cidr='10.96.0.0/16'),
                add_ons=oci.container_engine.models.AddOnOptions(is_kubernetes_dashboard_enabled=False))),
            opc_retry_token=token(state, 'cluster'))
        state['requests']['cluster'] = response.headers['opc-work-request-id']
        event(state, 'Actual Basic cluster creation submitted', work_request=state['requests']['cluster'],
            request_id=response.headers.get('opc-request-id'))
    wait_request(ce, state, 'cluster')
    if not state.get('cluster'):
        matches = [x for x in ce.list_clusters(compartment).data if x.name == NAME]
        if len(matches) != 1:
            raise RuntimeError('Cannot uniquely reconcile the created cluster')
        state['cluster'] = matches[0].id
        save(state)
    if not state.get('node_pool') and not state['requests'].get('node_pool'):
        pubkey = (Path.home() / '.oci/aegis-hosting/aegis-web-ed25519.pub').read_text(encoding='utf-8').strip()
        response = ce.create_node_pool(oci.container_engine.models.CreateNodePoolDetails(
            compartment_id=compartment, cluster_id=state['cluster'], name='ags-aegis-a1-node-pool',
            kubernetes_version=VERSION, node_shape='VM.Standard.A1.Flex', freeform_tags=TAGS,
            node_shape_config=oci.container_engine.models.CreateNodeShapeConfigDetails(ocpus=2, memory_in_gbs=12),
            node_source_details=oci.container_engine.models.NodeSourceViaImageDetails(
                image_id=source.image_id, boot_volume_size_in_gbs=50), ssh_public_key=pubkey,
            node_config_details=oci.container_engine.models.CreateNodePoolNodeConfigDetails(
                size=1, freeform_tags=TAGS, placement_configs=[oci.container_engine.models.NodePoolPlacementConfigDetails(
                    availability_domain=ad, subnet_id=state['worker_subnet'])]),
            node_pool_cycling_details=oci.container_engine.models.NodePoolCyclingDetails(is_node_cycling_enabled=False)),
            opc_retry_token=token(state, 'node_pool'))
        state['requests']['node_pool'] = response.headers['opc-work-request-id']
        event(state, 'Actual A1 node pool creation submitted', work_request=state['requests']['node_pool'],
            request_id=response.headers.get('opc-request-id'))
    wait_request(ce, state, 'node_pool')
    event(state, 'Approved OKE infrastructure creation completed')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        if STATE.exists():
            data = json.loads(STATE.read_text(encoding='utf-8'))
            detail = {'error_type': type(error).__name__, 'message': str(error)}
            event(data, 'Provisioning halted; no paid fallback selected', **detail)
        raise
