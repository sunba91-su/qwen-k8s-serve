terraform {
  required_providers {
    arvancloud = {
      source  = "terraform.arvancloud.ir/arvancloud/arvancloud"
    }
  }
}

provider "arvancloud" {
  api_key = var.arvan_api_key
}

resource "arvancloud_iaas_server" "k8s_master" {
  name      = "k8s-master-01"
  availability_zone    = var.region
  flavor_id    = "g3-4-2-0" 
  enable_ipv4 = true
  enable_ipv6 = false
  image_id  = var.image_id
  disk_size = 40
  enable_backup     = false
  ha_enabled = true
  key_name  = var.ssh_key_name

  security_groups   = ["fe30c283-b0a8-495d-91ee-6ae4c33cc320"]
  private_network_ids = []
}

resource "arvancloud_iaas_server" "k8s_workers" {
  availability_zone    = var.region
  count     = 2
  name      = "k8s-worker-0${count.index + 1}"
  flavor_id    = "g4-8-4-0" 
  enable_ipv4 = true
  enable_ipv6 = false
  ha_enabled = true
  image_id  = var.image_id
  enable_backup     = false
  disk_size = 60
  key_name  = var.ssh_key_name

  security_groups   = ["fe30c283-b0a8-495d-91ee-6ae4c33cc320"]
  private_network_ids = []
}