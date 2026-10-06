# Elektrokube Cilium and Flux

Cluster foundation for `elektrokube-scripts`: Cilium **1.20.2**, Flux **2.9.6**,
and Gateway API **1.6.2 experimental**. Application routes, SSO and storage are
managed in their own repositories. The experimental Gateway API channel is
required for SSO's native HTTPRoute ExternalAuth filter.

## October 2026 update

Flux was regenerated using the checksum-verified 2.9.6 CLI, preserving the four
standard controllers, dedicated-controller tolerations and strict substitutions.
Gateway API advances from 1.6.1 to 1.6.2; its experimental bundle SHA256 is
`fb03263a4a720cc7abe9b36ede6e308b558d2d725a39595d664f34fe37f9c503`.
The same version/checksum is in `elektrokube-scripts/config/cluster.json`.

Cilium, its CLI, and chart-owned Hubble UI are already at verified current releases.
Keep Cilium's chart-owned Envoy/operator/Relay/UI image versions and digests together.
Kubernetes 1.37 is outside Cilium 1.20.2's tested range; the scripts use the latest
1.36 patch, 1.36.5. See [Cilium compatibility](https://docs.cilium.io/en/stable/network/kubernetes/compatibility/),
[Flux release notes](https://github.com/fluxcd/flux2/releases/tag/v2.9.6), and
[Gateway API release notes](https://github.com/kubernetes-sigs/gateway-api/releases/tag/v1.6.2).

## Audit findings and rollout

The baseline `cdde1ba7d913cd4fb19aa309e1dbb76d9bec203a` had no CI workflow. This
branch adds chart rendering, strict schema validation, experimental ExternalAuth
schema checks, controller/toleration checks and retention/Helm-strategy checks.
The local result is **98 valid resources, zero invalid/errors/skipped**.

GitHub reports `main` unprotected with no repository rulesets. Because this source
manages cluster-admin controllers and networking, protect it with reviewed PRs,
required validation, restricted bypass and appropriate ownership of workflows and
networking manifests. No repository policy or cluster state was changed by this audit.

The first-node handoff intentionally lets Git replace live Cilium values and
versions. It checks release identity/ownership, but does not enforce an adjacent
minor upgrade or reject a downgrade. Review the actual installed Cilium version
and its supported upgrade path before first adoption. The old contract comment
claiming a matching-version/value check was corrected.

Keep orphaning/pruning exclusions for the CNI, shared CRDs and Flux itself: deleting
their Git path must not uninstall cluster networking or delete CRD instances. This
also means intentional removal needs an explicit cleanup procedure. Flux runs with
cluster-admin reconciliation authority; these repositories are not a tenant isolation
boundary. `API_IP` is still a single first-node endpoint. No HA VIP, Cilium transport
encryption or live failover test is supplied here.

Before merging into an automatically reconciled `main`, preserve recovery access,
back up etcd and its k3s token, and check existing reconciliation/cluster health.
Reconcile this foundation before the storage and SSO change branches. Require
current-revision Ready conditions for `flux-system`, `flux`, `gateway-api`, and
`cilium`, healthy controllers, Cilium connectivity, Accepted GatewayClass and
Programmed application Gateway/routes. Schema/render tests cannot prove the live
network datapath. Do not downgrade CRD schemas to the standard channel while
ExternalAuth routes are in use.

For the full four-repository audit and rollout plan, see
`elektrokube-scripts/docs/audit-2026-10-06.md` on the companion change branch.

## Offline validation

Requires Python with PyYAML, Helm, Kustomize and kubeconform. No cluster is contacted.

```sh
bash tests/install-tools.sh
PATH="$PWD/.cache/bin:$PATH" python3 tests/validate.py
```

The installer is for Linux amd64 CI and verifies exact tool archive checksums.
The validator downloads pinned upstream charts/CRD schemas and fails on unknown
schemas. CI uses checkout at an immutable commit with no persisted credentials.
