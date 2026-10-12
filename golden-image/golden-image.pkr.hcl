packer {
  required_plugins {
    qemu = {
      version = "~> 1.0"
      source  = "github.com/hashicorp/qemu"
    }
  }
}
source "qemu" "ubuntu_k8s" {
  iso_url           = "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
  iso_checksum      = "file:https://cloud-images.ubuntu.com/jammy/current/SHA256SUMS"
  output_directory  = "output-image"
  vm_name           = "k8s-golden-image.qcow2"
  format            = "qcow2"
  disk_size         = "20G"
  disk_interface    = "virtio"
  net_device        = "virtio-net"
  communicator      = "ssh"
  ssh_username      = "ubuntu"
  ssh_password      = "5a619bc4-073d-46f9-a23b-99f0d9446458"
  ssh_timeout       = "20m"
  headless          = true
  cd_files          = ["./cloud-data/user-data", "./cloud-data/meta-data"]
  cd_label          = "cidata"
}

build {
  sources = ["source.qemu.ubuntu_k8s"]
  provisioner "shell" {
    execute_command = "sudo sh -c '{{ .Vars }} {{ .Path }}'"
    script          = "./dependecies.sh"
  }
}