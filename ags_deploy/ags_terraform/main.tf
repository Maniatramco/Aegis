data "oci_identity_tenancy" "this" {
  tenancy_id = var.tenancy_ocid
}

data "oci_identity_regions" "all" {}

data "oci_objectstorage_namespace" "this" {
  compartment_id = var.tenancy_ocid
}

locals {
  home_region_key = data.oci_identity_tenancy.this.home_region_key
  home_region     = one([for r in data.oci_identity_regions.all.regions : r.name if r.key == local.home_region_key])
  region_key      = lower(one([for r in data.oci_identity_regions.all.regions : r.key if r.name == var.region]))
  compartment_id  = var.compartment_ocid != "" ? var.compartment_ocid : oci_identity_compartment.aegis[0].id
  namespace       = data.oci_objectstorage_namespace.this.namespace
  registry_host   = "${local.region_key}.ocir.io"
}

resource "oci_identity_compartment" "aegis" {
  count          = var.compartment_ocid == "" ? 1 : 0
  provider       = oci.home
  compartment_id = var.tenancy_ocid
  name           = var.compartment_name
  description    = "Aegis application"
  enable_delete  = false
  freeform_tags  = var.freeform_tags
}
