output "compartment_id" { value = local.compartment_id }
output "region" { value = var.region }
output "kubernetes_version" { value = local.kubernetes_version }
output "cluster_id" { value = oci_containerengine_cluster.aegis.id }
output "node_image" { value = split("|", local.node_image[0])[0] }
output "lb_subnet_id" {
  description = "Use for __LB_SUBNET_OCID__ in references/02-public-service.yaml."
  value       = oci_core_subnet.lb.id
}
output "registry_host" { value = local.registry_host }
output "tenancy_namespace" { value = local.namespace }
output "registry_prefix" { value = "${local.registry_host}/${local.namespace}" }
output "bucket" { value = oci_objectstorage_bucket.documents.name }
output "autonomous_database_id" { value = oci_database_autonomous_database.aegis.id }
output "db_name" { value = var.adb_db_name }
output "db_alias_low" { value = "${lower(var.adb_db_name)}_low" }

output "kubeconfig_command" {
  description = "Run on the operator machine to create a NEW kubeconfig for this cluster."
  value       = "oci ce cluster create-kubeconfig --cluster-id ${oci_containerengine_cluster.aegis.id} --file C:\\aegis-target\\kubeconfig.yaml --region ${var.region} --token-version 2.0.0 --kube-endpoint PUBLIC_ENDPOINT --profile ${var.oci_profile}"
}

output "wallet_command" {
  description = "Downloads the mTLS wallet zip; OCI CLI prompts for the new wallet password (it never enters Terraform state)."
  value       = "oci db autonomous-database generate-wallet --autonomous-database-id ${oci_database_autonomous_database.aegis.id} --file C:\\aegis-target\\Wallet_${var.adb_db_name}.zip --password-prompt --profile ${var.oci_profile}"
}

output "deployment_inputs" {
  description = "Paste into the private deployment JSON (ags_deploy/templates/deployment-inputs.example.json). ExpectedService comes from tnsnames.ora in the wallet."
  value = {
    Namespace         = "aegis-oci"
    Registry          = local.registry_host
    RegistryNamespace = local.namespace
    Platform          = local.arm ? "linux/arm64" : "linux/amd64"
    WalletPath        = "C:\\aegis-target\\Wallet_${var.adb_db_name}.zip"
    DBAdminUser       = "ADMIN"
    ServiceAlias      = "${lower(var.adb_db_name)}_low"
  }
}

output "seed_values" {
  description = "Non-secret values for scripts/seed_oci_state.py (skill section 7)."
  value = {
    AEGIS_SEED_DB_ALIAS         = "${lower(var.adb_db_name)}_low"
    AEGIS_SEED_DB_NAME          = var.adb_db_name
    AEGIS_SEED_REGION           = var.region
    AEGIS_SEED_BUCKET_NAMESPACE = local.namespace
    AEGIS_SEED_BUCKET           = oci_objectstorage_bucket.documents.name
  }
}
