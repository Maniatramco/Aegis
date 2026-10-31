# Same layout as the live pilot: one VCN, internet gateway, three public subnets
# (Kubernetes API, worker nodes, load balancers) with dedicated security lists.
locals {
  api_cidr    = cidrsubnet(var.vcn_cidr, 8, 0)
  worker_cidr = cidrsubnet(var.vcn_cidr, 8, 1)
  lb_cidr     = cidrsubnet(var.vcn_cidr, 8, 2)
}

resource "oci_core_vcn" "aegis" {
  compartment_id = local.compartment_id
  cidr_blocks    = [var.vcn_cidr]
  display_name   = "${var.name_prefix}-vcn"
  dns_label      = "agsaegis"
  freeform_tags  = var.freeform_tags
}

resource "oci_core_internet_gateway" "aegis" {
  compartment_id = local.compartment_id
  vcn_id         = oci_core_vcn.aegis.id
  display_name   = "${var.name_prefix}-ig"
  enabled        = true
  freeform_tags  = var.freeform_tags
}

resource "oci_core_route_table" "public" {
  compartment_id = local.compartment_id
  vcn_id         = oci_core_vcn.aegis.id
  display_name   = "${var.name_prefix}-public-routes"
  freeform_tags  = var.freeform_tags
  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.aegis.id
  }
}

resource "oci_core_security_list" "api" {
  compartment_id = local.compartment_id
  vcn_id         = oci_core_vcn.aegis.id
  display_name   = "${var.name_prefix}-api-security"
  freeform_tags  = var.freeform_tags

  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }
  dynamic "ingress_security_rules" {
    for_each = [6443, 12250]
    content {
      protocol = "6"
      source   = local.worker_cidr
      tcp_options {
        min = ingress_security_rules.value
        max = ingress_security_rules.value
      }
    }
  }
  ingress_security_rules {
    protocol = "6"
    source   = var.operator_cidr
    tcp_options {
      min = 6443
      max = 6443
    }
  }
}

resource "oci_core_security_list" "worker" {
  compartment_id = local.compartment_id
  vcn_id         = oci_core_vcn.aegis.id
  display_name   = "${var.name_prefix}-worker-security"
  freeform_tags  = var.freeform_tags

  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }
  # Control plane, other nodes and load balancer (health checks/NodePorts).
  dynamic "ingress_security_rules" {
    for_each = [local.api_cidr, local.worker_cidr, local.lb_cidr]
    content {
      protocol = "all"
      source   = ingress_security_rules.value
    }
  }
  ingress_security_rules {
    protocol = "6"
    source   = var.operator_cidr
    tcp_options {
      min = 22
      max = 22
    }
  }
}

resource "oci_core_security_list" "lb" {
  compartment_id = local.compartment_id
  vcn_id         = oci_core_vcn.aegis.id
  display_name   = "${var.name_prefix}-lb-security"
  freeform_tags  = var.freeform_tags

  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }
  dynamic "ingress_security_rules" {
    for_each = [80, 443]
    content {
      protocol = "6"
      source   = "0.0.0.0/0"
      tcp_options {
        min = ingress_security_rules.value
        max = ingress_security_rules.value
      }
    }
  }
}

resource "oci_core_subnet" "api" {
  compartment_id    = local.compartment_id
  vcn_id            = oci_core_vcn.aegis.id
  cidr_block        = local.api_cidr
  display_name      = "${var.name_prefix}-api-subnet"
  dns_label         = "api"
  route_table_id    = oci_core_route_table.public.id
  security_list_ids = [oci_core_security_list.api.id]
  freeform_tags     = var.freeform_tags
}

resource "oci_core_subnet" "worker" {
  compartment_id    = local.compartment_id
  vcn_id            = oci_core_vcn.aegis.id
  cidr_block        = local.worker_cidr
  display_name      = "${var.name_prefix}-worker-subnet"
  dns_label         = "worker"
  route_table_id    = oci_core_route_table.public.id
  security_list_ids = [oci_core_security_list.worker.id]
  freeform_tags     = var.freeform_tags
}

resource "oci_core_subnet" "lb" {
  compartment_id    = local.compartment_id
  vcn_id            = oci_core_vcn.aegis.id
  cidr_block        = local.lb_cidr
  display_name      = "${var.name_prefix}-lb-subnet"
  dns_label         = "lb"
  route_table_id    = oci_core_route_table.public.id
  security_list_ids = [oci_core_security_list.lb.id]
  freeform_tags     = var.freeform_tags
}
