#!/usr/bin/env bash

apt update
apt upgrade -y
apt install -y curl gnupg2 software-properties-common apt-transport-https ca-certificates

cat <<EOF | tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF
sysctl --system

apt install -y containerd
mkdir -p /etc/containerd
containerd config default | tee /etc/containerd/config.toml


sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
systemctl restart containerd
systemctl enable containerd

apt-get clean
rm -rf /var/lib/apt/lists/*