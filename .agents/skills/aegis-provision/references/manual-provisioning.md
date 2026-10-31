# Manual / Console provisioning reference

What the Terraform in `ags_deploy/ags_terraform/` creates, written out for review, Console creation, or a
tenancy where Terraform cannot be used. Creating any of this still requires gate G1 approval
(see `../SKILL.md`). Values are the live pilot's.

## Networking and OKE cluster

Use OCI Console (Networking, then Developer Services > Kubernetes Clusters > **Custom create**),
Terraform, or the OCI CLI. The retired pilot SDK helper did exactly this:

| Resource | Pilot setting |
| --- | --- |
| VCN | `ags-aegis-vcn`, `10.42.0.0/16`, DNS label `agsaegis` |
| Internet gateway + route table | `ags-aegis-ig`; route `0.0.0.0/0` -> IGW (all three subnets are public) |
| Subnet `api` (K8s API endpoint) | `10.42.0.0/24`, security list `ags-aegis-api-security` |
| Subnet `worker` (nodes) | `10.42.1.0/24`, security list `ags-aegis-worker-security` |
| Subnet `lb` (load balancers) | `10.42.2.0/24`, security list `ags-aegis-lb-security` |
| Egress (all lists) | all protocols to `0.0.0.0/0` |
| Ingress api | TCP 6443 and 12250 from `10.42.1.0/24`; TCP 6443 from operator `/32` |
| Ingress worker | all from `10.42.0.0/24`, `10.42.1.0/24`, `10.42.2.0/24`; TCP 22 from operator `/32` (32022 only for the optional relay) |
| Ingress lb | TCP 80 and 443 from `0.0.0.0/0` |
| Cluster | `BASIC_CLUSTER`, public API endpoint in `api` subnet, **Flannel overlay**, pods `10.244.0.0/16`, services `10.96.0.0/16`, service LB subnet = `lb`, dashboard off |
| Node pool | `ags-aegis-a1-node-pool`: 1 node, `VM.Standard.A1.Flex`, 2 OCPU, 12 GB, 50 GB boot, Oracle Linux 9 aarch64 OKE image matching the K8s version, node cycling off, operator SSH public key |
| Kubernetes version | `v1.36.4` observed. Pick a currently supported version |

Notes:
- Never expose the database or Ollama port 11434 publicly. Keep 6443 and 22 restricted to the operator `/32` (or use a private endpoint plus Bastion).
- The LB Service sets `security-list-management-mode: None`, so the worker list rule "all from lb subnet" is what lets LB health checks and NodePort traffic through. Keep it.
- For private worker nodes instead, add a NAT gateway and a Service gateway (OCIR, Object Storage). Nodes must reach OCIR, Object Storage, the ADB endpoint and `generativelanguage.googleapis.com:443`.

Kubeconfig for the new cluster (operator machine, new file, never overwrite the pilot's):

```powershell
oci ce cluster create-kubeconfig --cluster-id <cluster-ocid> --file C:\aegis-target\kubeconfig.yaml `
  --region <region> --token-version 2.0.0 --kube-endpoint PUBLIC_ENDPOINT --profile <operator-profile>
kubectl --kubeconfig C:\aegis-target\kubeconfig.yaml get nodes -o wide      # 1 node Ready, arm64
kubectl --kubeconfig C:\aegis-target\kubeconfig.yaml get storageclass        # oci-bv present
```

The pilot kubeconfig uses a private helper (`ags_deploy/ags_oke/ags_kubeconfig.py` together with a local `ags_runtime/ags_oke/provision-state.json`). That setup is not portable. Use the standard `oci ce` exec plugin above.

## IAM: groups, users and policies

Create in the tenancy (Identity domain > Groups/Users/Policies). Adjust names:

| Principal | Purpose | Credentials |
| --- | --- | --- |
| Group `aegis-operators` (people deploying) | Provision + release | Personal API key in OCI CLI profile, personal OCIR auth token for `docker login` |
| User `aegis-app` in group `aegis-app-runtime` | Backend access to Object Storage at runtime | API key pair whose `config` + PEM go into Secret `oci-credentials` |
| User `aegis-registry` in group `aegis-registry-pull` (or reuse operator) | OKE image pulls | Auth token in Secret `ocir-pull` |

Policies (compartment `aegis`; replace names). Pilot repositories were created at the
**tenancy root**, so if you do the same, write the repos statements `in tenancy`:

```
Allow group aegis-operators to manage virtual-network-family in compartment aegis
Allow group aegis-operators to manage cluster-family in compartment aegis
Allow group aegis-operators to manage instance-family in compartment aegis
Allow group aegis-operators to manage volume-family in compartment aegis
Allow group aegis-operators to manage load-balancers in compartment aegis
Allow group aegis-operators to manage autonomous-database-family in compartment aegis
Allow group aegis-operators to manage object-family in compartment aegis
Allow group aegis-operators to manage repos in compartment aegis
Allow group aegis-operators to use cloud-shell in tenancy
Allow group aegis-app-runtime to read buckets in compartment aegis
Allow group aegis-app-runtime to manage objects in compartment aegis where target.bucket.name='<bucket>'
Allow group aegis-registry-pull to read repos in compartment aegis
```

Add the OKE service policy if Console asks for it during cluster creation. Kubernetes
RBAC: the operator who generated the kubeconfig is cluster-admin. Add other operators with a
`ClusterRoleBinding` to their OCI user OCID.

## Autonomous AI Database and wallet

1. Create the **Autonomous AI Database** in the compartment: Oracle AI Database **26ai**
   (native `VECTOR`/`BOOLEAN` required), workload Transaction Processing. Pilot: `ags_ora_db`
   / DB name `agsora`, 1 ECPU, 20 GB, mTLS required. Size for real use. Set a private `ADMIN` password.
2. Network access: secure access from everywhere with mTLS (pilot), or an ACL/private endpoint
   that allows both the operator machine and the OKE worker subnet/NAT egress IP.
3. Download the **instance wallet** ZIP into `C:\aegis-target\wallet\` with a new wallet
   password. Record the TNS alias you will use (pilot `agsora_low`) and the full
   `SERVICE_NAME` from `tnsnames.ora`.
   Then continue with Phase 2 of the skill (schema).

## Object Storage bucket and OCIR repositories

- **Bucket:** Standard tier, private (the pilot's `ObjectRead` public access is an observation only, not a requirement), versioning
  as you choose. Pilot bucket `mk-aegis`, prefix `aegis`. Record namespace
  (`oci os ns get`), bucket and region.
- **OCIR:** create **private** repositories `ags-aegis-web` and `ags-aegis-backend`
  (pilot also has `ags-aegis-ssh`, which only the optional relay needs). Registry host is `<region-key>.ocir.io`
  (pilot `bom.ocir.io`, namespace `bmyljaecivrj`). Login username is
  `<tenancy-namespace>/<username>` (for a non-default identity domain: `<tenancy-namespace>/<domain>/<username>`).
  The password is an auth token.
