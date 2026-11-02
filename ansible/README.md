# Kubernetes bootstrap

This playbook bootstraps one control plane (`master`) and zero or more `workers`.
It requires Debian/Ubuntu, systemd, Python 3, and an installed/configured containerd
1.x runtime with the CRI registry section and its `config_path` key. It preserves
other containerd settings and refuses unsupported layouts rather than silently
skipping configuration. Containerd 2.x is not supported by this refactor.

## Run

Use ansible-core >=2.16 and collections compatible with your controller version
(the requirements ranges allow choosing compatible releases). From the repo root:

```bash
ansible-galaxy collection install -r ansible/requirements.yml
cp ansible/inventory.ini.example ansible/inventory.ini
# Edit inventory addresses, SSH identity, registry, and Kubernetes settings.
ansible-playbook -i ansible/inventory.ini ansible/k8s-setup.yml --syntax-check
ansible-playbook -i ansible/inventory.ini ansible/k8s-setup.yml --check --diff
ansible-playbook -i ansible/inventory.ini ansible/k8s-setup.yml
# Repeat against a disposable cluster: expect changed=0 when inputs/state are unchanged.
ansible-playbook -i ansible/inventory.ini ansible/k8s-setup.yml
```

No deployment is performed by syntax checking. Check mode previews supported tasks;
it cannot simulate package-dependent prerequisites on a fresh host and skips API
writes, join credential generation, and kubeconfig copying. A real disposable-host
run is required to verify bootstrap and second-run idempotency.

## Roles and inventory variables

- `kubernetes_node`: OS networking, swap, signed apt repository, held packages,
  existing containerd configuration, registry access, and service handlers.
- `kubernetes_control_plane`: guarded kubeadm init, private user kubeconfig, Calico
  reconciliation. The user home/group are discovered rather than hardcoded.
- `kubernetes_worker`: membership detection and short-lived join credentials only
  for unjoined workers. Credentials are created on the control plane, never cached
  as persistent facts, and suppressed from output.

Every public setting is in `roles/*/defaults/main.yml`; override in inventory,
`group_vars`, or `host_vars`. For lists/dictionaries use YAML group variables
adjacent to the inventory. Existing `registry_host`, `registry_username`, and
`registry_password` variables remain supported. Role-prefixed registry settings
can override them. Basic authorization headers replace the unsupported hosts.toml
`.auth` table. Credentials are stored root-only and hidden from task output/diffs.
Removing a registry host from inventory does not delete its existing credentials;
remove obsolete host directories explicitly during credential retirement.

Store secrets with Ansible Vault, for example:

```bash
mkdir -p ansible/group_vars/all
ansible-vault create ansible/group_vars/all/vault.yml
# Define registry_username and registry_password inside the encrypted file.
ansible-playbook -i ansible/inventory.ini ansible/k8s-setup.yml --ask-vault-pass
```

The retained v1.28/v3.26.1 defaults match the old playbook, not a recommendation
for a new production cluster. Select a compatible supported Kubernetes/Calico pair
in inventory. Exact package pinning is optional; package holds prevent incidental
upgrades. Changing a version is not a cluster upgrade workflow and held packages
are not force-unheld or downgraded. Pod CIDR/image repository settings are bootstrap
inputs; changing them does not reinitialize an existing cluster. Changing a Calico
pool after creation requires a dedicated migration, not merely editing inventory.
For custom Calico manifests, retain the standard commented CALICO_IPV4POOL_CIDR
stanza or provide a manifest whose pool already matches the configured CIDR.
An optional `kubernetes_control_plane_calico_checksum` accepts `sha256:...`.

## Failures and recovery

Each stage uses `block/rescue` and explicitly fails after reporting the task name.
Secrets and raw command arguments are not echoed by rescue. Preparation/control
plane failures stop subsequent plays. Ansible cannot rescue unreachable hosts or
parse errors. No automatic `kubeadm reset` is performed: partial initialization
requires inspection and potentially manual cleanup. Existing admin.conf and
kubelet.conf are membership guards; they do not prove cluster health or identity.
Do not use `--limit workers` to enroll new nodes unless the master is also present
in inventory and reachable for delegated token generation.

Package cache refreshes may report a change after cache expiry; external resource
drift is reconciled by Calico apply. The unchanged second-run target assumes no
cache expiry, input changes, cluster drift, or external file/service modifications.
After bootstrap, verify `kubectl get nodes` and Calico workloads with the installed
kubeconfig. API connectivity and workloads must be checked on real hosts.

References: [Ansible blocks/rescue](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_blocks.html),
[containerd registry hosts](https://github.com/containerd/containerd/blob/main/docs/hosts.md),
[kubeadm installation](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/).
