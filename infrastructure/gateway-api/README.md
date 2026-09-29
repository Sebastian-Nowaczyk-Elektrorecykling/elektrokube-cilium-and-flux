# Gateway API and external authorization

Flux installs the Gateway API **v1.6.1 experimental bundle** before reconciling
Cilium. The pinned Cilium **1.20.2** already supports the `ExternalAuth` HTTPRoute
filter, and `gatewayAPI.enabled`, `l7Proxy`, and Envoy are already enabled in
`../cilium/values.yaml`. No additional Cilium Helm flag is needed.

`ExternalAuth` is a filter within `HTTPRoute`, not a separate Kubernetes resource.
The standard bundle omits both the `ExternalAuth` filter type and its
`externalAuth` configuration schema. The experimental bundle supplies these
fields and includes the standard APIs, so only one bundle is installed.

Using the complete upstream bundle keeps all Gateway API schemas on the same
version and also exposes its other experimental fields and resources, including
`XBackend`, `XBackendTrafficPolicy`, and `XMesh`. Their presence does not imply
that Cilium implements every experimental feature. Use features supported by
the pinned Cilium release.

## Use ExternalAuth on an application route

Installing the CRDs makes the filter available; it does not protect existing
routes or deploy an authorization service. Add the filter to each application
route rule that needs protection and point it at your authorization service.

This example is documentation only and is not included in a Kustomization.
Replace the namespace, Gateway, hostname, Service names, ports, and headers with
your application's values. The example assumes the Gateway and both Services
already exist in the same namespace.

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: protected-app
  namespace: example-app
spec:
  parentRefs:
    - name: web
  hostnames:
    - app.example.com
  rules:
    - filters:
        - type: ExternalAuth
          externalAuth:
            protocol: HTTP
            backendRef:
              name: auth-service
              port: 9000
            http:
              allowedHeaders:
                - Cookie
              allowedResponseHeaders:
                - X-Authenticated-User
      backendRefs:
        - name: app
          port: 8080
```

The HTTP authorization service must return `200` to allow a request. Other
responses deny access, and communication failures must fail closed. The
`Authorization` header is sent automatically; `allowedHeaders` adds headers such
as `Cookie`. `http.path`, if configured, is a prefix added to the original request
path, not a replacement path. For gRPC authorization, use `protocol: GRPC` with
`grpc: {}` and an Envoy ext_authz-compatible backend. A backend in another
namespace also requires a `ReferenceGrant` in that backend's namespace.

## Reconcile and verify

After merging, Flux's existing dependency chain applies the CRDs before Cilium.
To reconcile immediately:

```sh
flux reconcile kustomization gateway-api --namespace flux-system --with-source
kubectl wait --for=condition=Ready kustomization/gateway-api \
  --namespace flux-system --timeout=5m
kubectl explain httproute.spec.rules.filters.externalAuth \
  --api-version=gateway.networking.k8s.io/v1
```

After configuring an application route, check its `Accepted` and `ResolvedRefs`
conditions for the Cilium parent and test both allowed and denied requests.
Also verify that an unavailable authorization backend denies requests.

Bootstrap can hand off an existing v1.6.1 standard installation; Flux upgrades
the schemas to the experimental channel. After handoff, keep CRD management in
Flux and do not reapply the standard bundle from a bootstrap rerun. Do not
downgrade to standard schemas while routes rely on experimental filters: losing
authorization configuration can remove protection. The existing `prune: false`
and `deletionPolicy: Orphan` settings retain shared CRDs on removal; they do not
make schema downgrades safe.

## Upstream references

- [Cilium 1.20 release announcement: External Authorization](https://github.com/cilium/cilium/discussions/47586)
- [Cilium Gateway API prerequisites and CRD installation](https://docs.cilium.io/en/stable/network/servicemesh/gateway-api/gateway-api/)
- [Gateway API v1.6.1 release and installation bundles](https://github.com/kubernetes-sigs/gateway-api/releases/tag/v1.6.1)
- [Pinned experimental HTTPRoute schema](https://github.com/kubernetes-sigs/gateway-api/blob/v1.6.1/config/crd/experimental/gateway.networking.k8s.io_httproutes.yaml)
