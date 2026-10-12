output "master_ip" {
  description = "Public IP address of the Kubernetes Master node"
  value       = arvancloud_iaas_server.k8s_master
}

output "worker_ips" {
  description = "Public IP addresses of the Kubernetes Worker nodes"
  value       = arvancloud_iaas_server.k8s_workers[*]
}