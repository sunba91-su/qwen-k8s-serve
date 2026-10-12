variable "arvan_api_key" {
  type        = string
  description = "ArvanCloud API Key for Authentication"
  sensitive   = true
}

variable "region" {
  type        = string
  default     = "ir-thr-c2"
  description = "ArvanCloud Region"
}

variable "ssh_key_name" {
  type        = string
  description = "name of the SSH key upload to ArvanCloud panel"
}

variable "image_id" {
  type        = string
  description = "ID of the custom Golden Image in ArvanCloud"
}