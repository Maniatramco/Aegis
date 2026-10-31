# Aegis OCI provisioning with Terraform

Creates the OCI infrastructure for a new Aegis destination, using the same layout as the live
Mumbai pilot. It provisions the infrastructure only. The first install (Kubernetes Secrets, seeding,
workloads) and later code releases follow `.agents/skills/aegis-oci-replicate/SKILL.md`
sections 6-9 and `Deploy-Aegis.ps1`.

## What it creates

| File | Resources |
| --- | --- |
| `main.tf` | Compartment `aegis` (only if `compartment_ocid` is empty) |
| `network.tf` | VCN `10.42.0.0/16`, internet gateway, route table, subnets api/worker/lb (`.0/.1/.2.0/24`), security lists identical to the pilot (6443 and 22 only from `operator_cidr`, 80/443 public on the LB subnet) |
| `oke.tf` | OKE **Basic** cluster (Flannel, public API endpoint, pods `10.244.0.0/16`, services `10.96.0.0/16`) and a node pool with 1x `VM.Standard.A1.Flex`, 2 OCPU, 12 GB, 50 GB boot, using the newest Oracle Linux OKE image for the chosen version and architecture |
| `database.tf` | Autonomous AI Database **26ai**, OLTP, mTLS, 2 ECPU and 20 GB by default (or Always Free). `prevent_destroy` is on |
| `storage.tf` | Private Standard bucket (`prevent_destroy`), private OCIR repositories `ags-aegis-web`, `ags-aegis-backend` |
| `iam.tf` | Optional (`create_iam = true`): groups `aegis-operators`, `aegis-app-runtime`, `aegis-registry-pull`; users `aegis-app`, `aegis-registry`; policy `aegis-policies` |

It does **not** create (by design, to keep secrets out of state): the wallet file and its password, API private keys,
OCIR auth tokens, the DB application user and tables (`Deploy-Aegis.ps1` with `DB_Object=Y`), Kubernetes objects,
the load balancer (created by the `aegis-public` Service) and model registrations (done in the browser after install).

## Minimal input

Three values in `terraform.tfvars`, plus the ADB ADMIN password at a prompt:

```powershell
cd ags_deploy\ags_terraform
Copy-Item terraform.tfvars.example terraform.tfvars
notepad terraform.tfvars        # tenancy_ocid, region, operator_cidr
.\Provision-Aegis.ps1 -PlanOnly # plan only: lists every resource, sizing and cost note; changes nothing
.\Provision-Aegis.ps1           # same plan, then waits for you to type PROVISION before applying
terraform output
```

**Approval is mandatory.** `Provision-Aegis.ps1` applies only the saved, reviewed plan and only after the operator
types `PROVISION` interactively (plus `DESTROY` if the plan would remove or replace anything). Redirected or piped input
is refused. Do not use `terraform apply -auto-approve`. An AI agent must show the plan and get the human's approval
first, and must never type the approval word itself.

Prerequisites: Terraform 1.5 or newer, OCI CLI configured (`oci setup config`) with a user that can manage the compartment
(tenancy admin if `create_iam = true` or a new compartment is created). Provider auth comes from
`~/.oci/config` (`oci_profile`, default `DEFAULT`).

**State contains the ADMIN password** (OCI requires it at creation) and every OCID. Keep `terraform.tfstate` private
(it is git-ignored) or use an OCI Object Storage backend with restricted access. Change the ADMIN password in Console after
creation if you prefer; Terraform ignores later changes to it.

## After apply

```powershell
terraform output -raw kubeconfig_command | Invoke-Expression   # writes C:\aegis-target\kubeconfig.yaml
terraform output -raw wallet_command     | Invoke-Expression   # prompts for a NEW wallet password
terraform output deployment_inputs                              # values for the private deployment JSON
terraform output seed_values                                    # values for the seed step
terraform output lb_subnet_id                                   # for 02-public-service.yaml
```

Then continue with the skill: section 4 step 4 (create the schema), then sections 6-9.

## Notes

- If A1 capacity is unavailable in the first availability domain, set `availability_domain_index = 1` (or 2).
- Leaving `kubernetes_version` empty takes the newest version OCI offers at plan time. Pin it for repeatable runs.
  Later image updates do not replace the node (`ignore_changes`).
- `terraform destroy` stops at the database and the bucket because of `prevent_destroy`. Remove that deliberately if you really want to delete them.
- The lock file covers Windows, Linux and macOS for provider `oracle/oci` 9.11.0.
