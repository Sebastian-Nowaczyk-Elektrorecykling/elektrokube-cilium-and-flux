#!/usr/bin/env python3
"""Validate Flux, Gateway API and rendered Cilium without a live cluster."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import yaml

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache/validation'
SCHEMAS = CACHE / 'schemas'
KUBE_VERSION = '1.36.4'


def run(*args):
    return subprocess.check_output(args, text=True, cwd=ROOT)


def docs(text):
    return [d for d in yaml.safe_load_all(text) if d]


def fetch(url, filename):
    path = CACHE / filename
    if not path.exists():
        with urllib.request.urlopen(url, timeout=60) as response:
            path.write_bytes(response.read())
    return path.read_bytes()


def main():
    os.umask(0o077)
    SCHEMAS.mkdir(parents=True, exist_ok=True)
    gateway = yaml.safe_load((ROOT / 'infrastructure/gateway-api/kustomization.yaml').read_text())
    bundle = fetch(gateway['resources'][0], 'gateway-v1.6.2.yaml')
    assert hashlib.sha256(bundle).hexdigest() == 'fb03263a4a720cc7abe9b36ede6e308b558d2d725a39595d664f34fe37f9c503'
    route_crd = next(d for d in docs(bundle) if d['metadata']['name'] == 'httproutes.gateway.networking.k8s.io')
    v1 = next(v for v in route_crd['spec']['versions'] if v['name'] == 'v1' and v['served'])
    filters = v1['schema']['openAPIV3Schema']['properties']['spec']['properties']['rules']['items']['properties']['filters']['items']['properties']
    assert 'externalAuth' in filters, 'SSO needs the experimental HTTPRoute schema'
    resources = {}
    for path in sorted(ROOT.rglob('kustomization.yaml')):
        if any(p.startswith('.') for p in path.relative_to(ROOT).parts):
            continue
        output = run('kustomize', 'build', str(path.parent))
        output = output.replace('${API_IP}', '192.0.2.10').replace('${CLUSTER_NAME}', 'validation')
        # Upstream CRD descriptions contain literal substitution examples.
        # Only the Cilium workload values are subject to our substitutions.
        if path.parent == ROOT / 'infrastructure/cilium':
            assert '${' not in output
        for d in docs(output):
            key = (d['apiVersion'], d['kind'], d['metadata'].get('namespace'), d['metadata']['name'])
            assert key not in resources or resources[key] == d, f'Conflicting resource {key}'
            resources[key] = d
    manifests = list(resources.values())
    controllers = [d for d in manifests if d['kind'] == 'Deployment']
    assert {d['metadata']['name'] for d in controllers} == {
        'source-controller', 'kustomize-controller', 'helm-controller', 'notification-controller'}
    for controller in controllers:
        assert {'key': 'CriticalAddonsOnly', 'operator': 'Exists'} in controller['spec']['template']['spec']['tolerations']
    kustomize = next(d for d in controllers if d['metadata']['name'] == 'kustomize-controller')
    assert '--feature-gates=StrictPostBuildSubstitutions=true' in kustomize['spec']['template']['spec']['containers'][0]['args']
    release = next(d for d in manifests if d['kind'] == 'HelmRelease')
    spec = release['spec']
    assert spec['releaseName'] == 'cilium' and spec['targetNamespace'] == spec['storageNamespace'] == 'kube-system'
    assert all(spec[a]['strategy']['name'] == 'RetryOnFailure' for a in ('install', 'upgrade'))
    assert all(not d['spec']['prune'] for d in manifests if d['kind'] == 'Kustomization')
    values_name = spec['valuesFrom'][0]['name']
    values = next(d['data']['values.yaml'] for d in manifests if d['kind'] == 'ConfigMap' and d['metadata']['name'] == values_name)
    value_file = CACHE / 'cilium-values.yaml'; value_file.write_text(values)
    chart = spec['chart']['spec']; archive = CACHE / f"cilium-{chart['version']}.tgz"
    if not archive.exists():
        run('helm', 'pull', 'cilium', '--repo', 'https://helm.cilium.io', '--version', chart['version'], '--destination', str(CACHE))
    rendered = docs(run('helm', 'template', 'cilium', str(archive), '--namespace', 'kube-system', '--values', str(value_file), '--kube-version', KUBE_VERSION))
    manifests.extend(rendered)
    for d in manifests:
        if d['kind'] != 'CustomResourceDefinition':
            continue
        crd = d['spec']
        for version in crd['versions']:
            schema = version.get('schema', {}).get('openAPIV3Schema')
            if schema:
                (SCHEMAS / f"{crd['group']}_{crd['names']['kind'].lower()}_{version['name']}.json").write_text(json.dumps(schema))
    for group, kinds in {
        'apiextensions.k8s.io': {'CustomResourceDefinition': 'io.k8s.apiextensions-apiserver.pkg.apis.apiextensions.v1.CustomResourceDefinition'},
        'admissionregistration.k8s.io': {k: f'io.k8s.api.admissionregistration.v1.{k}' for k in ('ValidatingAdmissionPolicy', 'ValidatingAdmissionPolicyBinding')},
    }.items():
        api = json.loads(fetch(f'https://raw.githubusercontent.com/kubernetes/kubernetes/v{KUBE_VERSION}/api/openapi-spec/v3/apis__{group}__v1_openapi.json', f'{group}.json'))
        definitions = json.loads(json.dumps(api['components']['schemas']).replace('#/components/schemas/', '#/definitions/'))
        for kind, definition in kinds.items():
            (SCHEMAS / f'{group}_{kind.lower()}_v1.json').write_text(json.dumps({'$ref': '#/definitions/' + definition, 'definitions': definitions}))
    target = CACHE / 'all.yaml'; target.write_text(yaml.safe_dump_all(manifests, sort_keys=False))
    print(f'Rendered Cilium {chart["version"]}: {len(rendered)} resources', flush=True)
    print(run('kubeconform', '-strict', '-summary', '-kubernetes-version', KUBE_VERSION,
              '-schema-location', str(SCHEMAS / '{{.Group}}_{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'),
              '-schema-location', 'default', str(target)), end='')


if __name__ == '__main__':
    main()
