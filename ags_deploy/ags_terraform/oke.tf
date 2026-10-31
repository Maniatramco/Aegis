data "oci_containerengine_cluster_option" "all" {
  cluster_option_id = "all"
  compartment_id    = local.compartment_id
}

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

locals {
  # Newest offered version unless one is pinned.
  k8s_versions       = data.oci_containerengine_cluster_option.all.kubernetes_versions
  kubernetes_version = var.kubernetes_version != "" ? var.kubernetes_version : local.k8s_versions[length(local.k8s_versions) - 1]
  arm                = length(regexall("A1|A2|A4", var.node_shape)) > 0
}

data "oci_containerengine_node_pool_option" "for_version" {
  node_pool_option_id = oci_containerengine_cluster.aegis.id
  compartment_id      = local.compartment_id
}

locals {
  # Oracle Linux OKE image for this Kubernetes version and CPU architecture.
  node_images = [
    for s in data.oci_containerengine_node_pool_option.for_version.sources : s
    if s.source_type == "IMAGE"
    && length(regexall("OKE-${trimprefix(local.kubernetes_version, "v")}-", s.source_name)) > 0
    && length(regexall("Oracle-Linux", s.source_name)) > 0
    && length(regexall("GPU", s.source_name)) == 0
    && (local.arm ? length(regexall("aarch64", s.source_name)) > 0 : length(regexall("aarch64", s.source_name)) == 0)
  ]
  node_image = reverse(sort([for s in local.node_images : "${s.source_name}|${s.image_id}"]))
}

resource "oci_containerengine_cluster" "aegis" {
  compartment_id     = local.compartment_id
  name               = "${var.name_prefix}-basic"
  vcn_id             = oci_core_vcn.aegis.id
  kubernetes_version = local.kubernetes_version
  type               = "BASIC_CLUSTER"
  freeform_tags      = var.freeform_tags

  endpoint_config {
    subnet_id            = oci_core_subnet.api.id
    is_public_ip_enabled = true
  }

  cluster_pod_network_options {
    cni_type = "FLANNEL_OVERLAY"
  }

  options {
    service_lb_subnet_ids = [oci_core_subnet.lb.id]
    kubernetes_network_config {
      pods_cidr     = var.pods_cidr
      services_cidr = var.services_cidr
    }
    add_ons {
      is_kubernetes_dashboard_enabled = false
      is_tiller_enabled               = false
    }
  }
}

resource "oci_containerengine_node_pool" "aegis" {
  compartment_id     = local.compartment_id
  cluster_id         = oci_containerengine_cluster.aegis.id
  name               = "${var.name_prefix}-node-pool"
  kubernetes_version = local.kubernetes_version
  node_shape         = var.node_shape
  ssh_public_key     = var.node_ssh_public_key != "" ? var.node_ssh_public_key : null
  freeform_tags      = var.freeform_tags

  node_shape_config {
    ocpus         = var.node_ocpus
    memory_in_gbs = var.node_memory_gbs
  }

  node_source_details {
    source_type             = "IMAGE"
    image_id                = split("|", local.node_image[0])[1]
    boot_volume_size_in_gbs = var.node_boot_volume_gbs
  }

  node_config_details {
    size = var.node_count
    placement_configs {
      availability_domain = data.oci_identity_availability_domains.ads.availability_domains[var.availability_domain_index].name
      subnet_id           = oci_core_subnet.worker.id
    }
  }

  lifecycle {
    precondition {
      condition     = length(local.node_image) > 0
      error_message = "No Oracle Linux OKE node image matches this Kubernetes version and shape architecture. Pin kubernetes_version to a version that has one."
    }
    # A newer image appearing later must not replace the running node.
    ignore_changes = [node_source_details[0].image_id]
  }
}
