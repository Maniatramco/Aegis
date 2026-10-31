# Autonomous AI Database 26ai (native VECTOR/BOOLEAN), mTLS wallet access as in the pilot.
# The app user and 13 tables are NOT created here: run Deploy-Aegis.ps1 with DB_Object=Y
# (see the aegis-provision skill, Phase 2). The wallet is downloaded with the
# OCI CLI command in the outputs so its password never enters Terraform state.
resource "oci_database_autonomous_database" "aegis" {
  compartment_id              = local.compartment_id
  display_name                = "${var.name_prefix}-db"
  db_name                     = var.adb_db_name
  db_version                  = var.adb_db_version
  db_workload                 = "OLTP"
  admin_password              = var.adb_admin_password
  is_free_tier                = var.adb_is_free_tier
  compute_model               = var.adb_is_free_tier ? null : "ECPU"
  compute_count               = var.adb_is_free_tier ? null : var.adb_ecpu
  data_storage_size_in_gb     = var.adb_is_free_tier ? null : var.adb_storage_gbs
  is_auto_scaling_enabled     = false
  is_mtls_connection_required = true
  license_model               = var.adb_is_free_tier ? null : "LICENSE_INCLUDED"
  freeform_tags               = var.freeform_tags

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [admin_password]
  }
}
