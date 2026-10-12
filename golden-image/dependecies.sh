#!/usr/bin/env bash
apt update
apt upgrade -y
apt install -y curl gnupg2 software-properties-common apt-transport-https ca-certificates
