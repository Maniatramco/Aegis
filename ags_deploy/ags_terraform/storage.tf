resource "oci_objectstorage_bucket" "documents" {
  compartment_id = local.compartment_id
  namespace      = local.namespace
  name           = var.bucket_name
  access_type    = "NoPublicAccess"
  storage_tier   = "Standard"
  versioning     = var.bucket_versioning
  freeform_tags  = var.freeform_tags

  lifecycle {
    prevent_destroy = true
  }
}

# Private image repositories. Release tooling pushes ags-aegis-web and ags-aegis-backend.
resource "oci_artifacts_container_repository" "repos" {
  for_each       = toset(["ags-aegis-web", "ags-aegis-backend"])
  compartment_id = local.compartment_id
  display_name   = each.key
  is_public      = false
  is_immutable   = false
  freeform_tags  = var.freeform_tags
}
