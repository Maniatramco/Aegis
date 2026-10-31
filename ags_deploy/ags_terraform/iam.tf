# Optional (create_iam = true). Requires tenancy administrator rights; created in the home region.
# Terraform never creates API private keys or auth tokens (they would land in state):
#  - aegis-app API key: generate locally, pass only the PUBLIC key via app_user_public_key_pem.
#  - aegis-registry auth token: create in Console/CLI and use it for the ocir-pull Secret.
locals {
  compartment_name = var.compartment_ocid != "" ? data.oci_identity_compartment.existing[0].name : var.compartment_name
}

data "oci_identity_compartment" "existing" {
  count = var.compartment_ocid != "" ? 1 : 0
  id    = var.compartment_ocid
}

resource "oci_identity_group" "groups" {
  for_each       = var.create_iam ? toset([var.operator_group_name, "aegis-app-runtime", "aegis-registry-pull"]) : toset([])
  provider       = oci.home
  compartment_id = var.tenancy_ocid
  name           = each.key
  description    = "Aegis ${each.key}"
  freeform_tags  = var.freeform_tags
}

resource "oci_identity_user" "app" {
  count          = var.create_iam ? 1 : 0
  provider       = oci.home
  compartment_id = var.tenancy_ocid
  name           = "aegis-app"
  description    = "Aegis backend runtime identity (Object Storage)"
  freeform_tags  = var.freeform_tags
}

resource "oci_identity_user" "registry" {
  count          = var.create_iam ? 1 : 0
  provider       = oci.home
  compartment_id = var.tenancy_ocid
  name           = "aegis-registry"
  description    = "Aegis OKE image pulls"
  freeform_tags  = var.freeform_tags
}

resource "oci_identity_user_group_membership" "app" {
  count    = var.create_iam ? 1 : 0
  provider = oci.home
  group_id = oci_identity_group.groups["aegis-app-runtime"].id
  user_id  = oci_identity_user.app[0].id
}

resource "oci_identity_user_group_membership" "registry" {
  count    = var.create_iam ? 1 : 0
  provider = oci.home
  group_id = oci_identity_group.groups["aegis-registry-pull"].id
  user_id  = oci_identity_user.registry[0].id
}

resource "oci_identity_api_key" "app" {
  count     = var.create_iam && var.app_user_public_key_pem != "" ? 1 : 0
  provider  = oci.home
  user_id   = oci_identity_user.app[0].id
  key_value = var.app_user_public_key_pem
}

resource "oci_identity_policy" "aegis" {
  count          = var.create_iam ? 1 : 0
  provider       = oci.home
  compartment_id = var.tenancy_ocid
  name           = "aegis-policies"
  description    = "Aegis operators, runtime and image pulls"
  freeform_tags  = var.freeform_tags
  statements = [
    "Allow group ${var.operator_group_name} to manage virtual-network-family in compartment ${local.compartment_name}",
    "Allow group ${var.operator_group_name} to manage cluster-family in compartment ${local.compartment_name}",
    "Allow group ${var.operator_group_name} to manage instance-family in compartment ${local.compartment_name}",
    "Allow group ${var.operator_group_name} to manage volume-family in compartment ${local.compartment_name}",
    "Allow group ${var.operator_group_name} to manage load-balancers in compartment ${local.compartment_name}",
    "Allow group ${var.operator_group_name} to manage autonomous-database-family in compartment ${local.compartment_name}",
    "Allow group ${var.operator_group_name} to manage object-family in compartment ${local.compartment_name}",
    "Allow group ${var.operator_group_name} to manage repos in compartment ${local.compartment_name}",
    "Allow group ${var.operator_group_name} to use cloud-shell in tenancy",
    "Allow group aegis-app-runtime to read buckets in compartment ${local.compartment_name}",
    "Allow group aegis-app-runtime to manage objects in compartment ${local.compartment_name} where target.bucket.name='${var.bucket_name}'",
    "Allow group aegis-registry-pull to read repos in compartment ${local.compartment_name}",
  ]
  depends_on = [oci_identity_group.groups]
}
