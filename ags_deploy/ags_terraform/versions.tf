terraform {
  required_version = ">= 1.5.0"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 6.0.0, < 10.0.0"
    }
  }
}

# Authentication comes from the operator's OCI CLI profile (~/.oci/config).
# Nothing secret is configured here.
provider "oci" {
  region              = var.region
  config_file_profile = var.oci_profile
}

# IAM resources must be created in the home region.
provider "oci" {
  alias               = "home"
  region              = local.home_region
  config_file_profile = var.oci_profile
}
