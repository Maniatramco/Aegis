# ---- Required ---------------------------------------------------------------
variable "tenancy_ocid" {
  description = "Tenancy OCID (from ~/.oci/config)."
  type        = string
}

variable "region" {
  description = "Target region, e.g. ap-hyderabad-1."
  type        = string
}

variable "operator_cidr" {
  description = "Operator public IP as /32. Only this address may reach the Kubernetes API (6443) and node SSH (22)."
  type        = string
  validation {
    condition     = can(cidrhost(var.operator_cidr, 0))
    error_message = "Use CIDR notation, e.g. 203.0.113.10/32."
  }
}

variable "adb_admin_password" {
  description = "ADMIN password for the Autonomous AI Database. Supply via TF_VAR_adb_admin_password or the prompt; it is stored in Terraform state, so keep state private."
  type        = string
  sensitive   = true
}

# ---- Compartment --------------------------------------------------------------
variable "compartment_ocid" {
  description = "Existing compartment OCID. Leave empty to create a new compartment named compartment_name under the tenancy root."
  type        = string
  default     = ""
}

variable "compartment_name" {
  type    = string
  default = "aegis"
}

variable "oci_profile" {
  description = "Profile in ~/.oci/config used by Terraform."
  type        = string
  default     = "DEFAULT"
}

variable "name_prefix" {
  description = "Prefix for every resource display name."
  type        = string
  default     = "ags-aegis"
}

# ---- Network (pilot values) -----------------------------------------------------
variable "vcn_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "pods_cidr" {
  type    = string
  default = "10.244.0.0/16"
}

variable "services_cidr" {
  type    = string
  default = "10.96.0.0/16"
}

# ---- OKE (pilot values) ------------------------------------------------------------
variable "kubernetes_version" {
  description = "OKE version, e.g. v1.34.1. Empty = newest version OCI offers."
  type        = string
  default     = ""
}

variable "node_shape" {
  type    = string
  default = "VM.Standard.A1.Flex"
}

variable "node_ocpus" {
  type    = number
  default = 2
}

variable "node_memory_gbs" {
  type    = number
  default = 12
}

variable "node_count" {
  description = "Keep 1: API and worker share one ReadWriteOnce volume."
  type        = number
  default     = 1
}

variable "node_boot_volume_gbs" {
  type    = number
  default = 50
}

variable "availability_domain_index" {
  description = "Which availability domain (0-based) to place the node in; change it if A1 capacity is unavailable."
  type        = number
  default     = 0
}

variable "node_ssh_public_key" {
  description = "Optional SSH public key for the worker node."
  type        = string
  default     = ""
}

# ---- Database ---------------------------------------------------------------------
variable "adb_db_name" {
  description = "Database name (letters/digits, max 14). The wallet aliases become <name>_low/_medium/_high/_tp/_tpurgent."
  type        = string
  default     = "agsora"
}

variable "adb_ecpu" {
  type    = number
  default = 2
}

variable "adb_storage_gbs" {
  type    = number
  default = 20
}

variable "adb_is_free_tier" {
  description = "Use an Always Free ADB (fixed small size) if the tenancy still has one available."
  type        = bool
  default     = false
}

variable "adb_db_version" {
  type    = string
  default = "26ai"
}

# ---- Storage and registry -----------------------------------------------------------------
variable "bucket_name" {
  type    = string
  default = "aegis-documents"
}

variable "bucket_versioning" {
  type    = string
  default = "Disabled"
}

# ---- IAM (optional; needs tenancy administrator rights) ---------------------------------------
variable "create_iam" {
  description = "Create groups, the aegis-app and aegis-registry users, memberships and policies."
  type        = bool
  default     = false
}

variable "operator_group_name" {
  type    = string
  default = "aegis-operators"
}

variable "app_user_public_key_pem" {
  description = "Optional PEM public key to attach to the aegis-app user (the private key stays on your machine and goes into the oci-credentials Secret)."
  type        = string
  default     = ""
}

variable "freeform_tags" {
  type    = map(string)
  default = { application = "Aegis" }
}
