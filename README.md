# qwen-k8s-serve

CPU-only text generation with Qwen2.5, vLLM, Ray Serve, and Kubernetes, developed for the **ArvanCloud SRE technical challenge**.

The repository covers building an Ubuntu golden image, provisioning three ArvanCloud VMs with Terraform, bootstrapping Kubernetes with Ansible, and deploying a single model-serving replica through KubeRay. A FastAPI application provides a small generation API and a subset of the OpenAI completions API.

**Status:** the repository contains the infrastructure and serving implementation, a manifest deployment workflow, a ServiceMonitor, and a basic load-test script. Several setup steps remain manual. Live availability, monitoring coverage, and performance results must be verified against the deployed environment; this README does not claim an end-to-end validated rebuild or production readiness.

## Contents

- [Architecture](#architecture)
- [Repository layout](#repository-layout)
- [Prerequisites](#prerequisites)
- [Deployment](#deployment)
- [API usage](#api-usage)
- [Delivery workflow](#delivery-workflow)
- [Monitoring](#monitoring)
- [Load testing](#load-testing)
- [Troubleshooting](#troubleshooting)
- [Security and limitations](#security-and-limitations)
- [Teardown](#teardown)
- [AI usage and license](#ai-usage-and-license)

## Architecture

Terraform defines one control-plane VM (`k8s-master-01`) and two worker VMs (`k8s-worker-01` and `k8s-worker-02`). Ansible installs Kubernetes packages from the v1.28 repository, initializes the control plane with kubeadm, installs Calico v3.26.1, and joins the workers. The golden image supplies containerd with the systemd cgroup driver.

The application manifest defines a `RayService` named `qwen-vllm-service` in the `default` namespace. It contains **one Ray head and no Ray worker groups**. The single Serve replica and vLLM engine therefore run on the Ray head. Kubernetes chooses its node; the manifest has no node affinity, node selector, or inference-specific tolerations.

Requests enter through the `qwen-vllm-serve` NodePort Service on port **30800**, reach the Ray Serve HTTP proxy on port 8000, and are routed to the FastAPI ingress and vLLM engine. No Ingress or TLS configuration is committed.

Model files come from the node-local directory `/opt/models/hub`, mounted at `/models`. Offline Hugging Face settings require that cache to be populated before startup. There is no PVC, download Job, or init container. Rescheduling onto a different node requires the cache to exist there too.

### Runtime configuration

The committed configuration uses:

- Model: `Qwen/Qwen2.5-0.5B-Instruct`, CPU inference, default dtype `float32`.
- Runtime: Ray 2.40.0, Python 3.10 base image, vLLM 0.17.0 CPU wheel.
- Ray head container: requests and limits of 2 CPU and 6 GiB memory.
- Serve: one replica, 2 logical Ray CPUs, `max_ongoing_requests: 2`.
- Engine: `MAX_MODEL_LEN=512`, `MAX_NUM_SEQS=1`, `KV_CACHE_GIB=1`.
- CPU threading: `OMP_NUM_THREADS=1`, `VLLM_CPU_OMP_THREADS_BIND=nobind`.

The manifest's Serve configuration overrides the Python deployment's CPU allocation, despite `REPLICA_NUM_CPUS=1` in the container environment. Python defaults also differ from Kubernetes settings; inspect [serve_script.py](endpoint/serve_script.py), [Dockerfile](endpoint/Dockerfile), and [vllm-deployment.yaml](kubernetes/vllm-deployment.yaml) together when tuning.

A single control plane and a single serving replica are availability constraints. The cloud VM `ha_enabled` setting does not make the Kubernetes control plane or application highly available.

## Repository layout

```text
.
├── golden-image/
│   ├── golden-image.pkr.hcl   # Packer QEMU image build
│   ├── dependecies.sh         # OS packages and containerd configuration
│   └── cloud-data/            # NoCloud initialization data
├── terraform/
│   ├── main.tf               # Three ArvanCloud VM resources
│   ├── variables.tf
│   ├── outputs.tf
│   └── terraform.tfvars.example
├── ansible/
│   ├── k8s-setup.yml          # OS networking, kubeadm, Calico, worker join
│   └── inventory.ini.example
├── endpoint/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── serve_config.yaml     # Standalone Ray Serve configuration
│   └── serve_script.py       # FastAPI ingress and vLLM integration
├── kubernetes/
│   └── vllm-deployment.yaml   # RayService, NodePort Service, ServiceMonitor
├── load-test/
│   ├── env.example
│   └── load_test.sh
├── .github/workflows/deploy.yml
├── docs/ai-usage.md
├── LICENSE
└── README.md
```

## Prerequisites

On the operator workstation, install Git, Packer with its QEMU plugin, QEMU and the tools needed to create the NoCloud CD image, Terraform, Ansible, kubectl, Helm, Docker, Python with pip, and an SSH client. The load test requires Bash, curl, seq, and xargs. Tool versions are not comprehensively pinned in this repository.

You also need:

- An ArvanCloud account, API key, an uploaded SSH public key, and capacity for three VMs.
- An uploaded custom image built from `golden-image/`.
- An existing security group suitable for the cluster. Replace the hard-coded security-group IDs in `terraform/main.tf` with IDs from your account and review its rules.
- A registry you can push to and the cluster can pull from. The Dockerfile currently uses a custom mirror for its Ray base image; replace it if unavailable.
- Network access to package repositories, image registries, and model files during preparation.
- CPU instruction support compatible with the vLLM CPU wheel. Inspect `lscpu` on candidate hosts and validate engine startup before running benchmarks.

Terraform defaults to region `ir-thr-c2`. It requests flavor `g3-4-2-0` with a 40 GiB disk for the control plane and `g4-8-4-0` with 60 GiB disks for both workers. Confirm the actual CPU and RAM specifications and flavor availability in your account. Terraform references existing SSH keys and security groups; it does not create those resources or a private network.

## Deployment

Run commands from the repository root unless a step explicitly changes directory. These steps describe the committed implementation and call out the configuration and external prerequisites needed to reproduce it.

### 1. Build and upload the golden image

The Packer template starts from an Ubuntu 22.04 cloud image. Its shell provisioner installs containerd and sets `SystemdCgroup = true`.

**Before building:** replace the fixed build password in both the Packer template and `cloud-data/user-data`. Password-based SSH is enabled by the committed cloud-init configuration. Ensure temporary build credentials are removed and password login is disabled in the image used for deployment; the current scripts do not automate this cleanup.

```bash
cd golden-image
packer init .
packer validate .
packer build .
cd ..
```

The output is `golden-image/output-image/k8s-golden-image.qcow2`. Upload it as a custom image to ArvanCloud using your account's image workflow and record its image ID. Uploading is a manual step outside the Terraform configuration.

### 2. Provision the VMs

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
```

Set `region`, `ssh_key_name`, and `image_id` in that file. Remove its placeholder `arvan_api_key` assignment if supplying the key through `TF_VAR_arvan_api_key`; Terraform variable files take precedence over environment variables. Keep actual credentials out of committed files.

After replacing the security-group IDs in `terraform/main.tf`:

```bash
terraform -chdir=terraform init
terraform -chdir=terraform plan -out=tfplan
terraform -chdir=terraform apply tfplan
terraform -chdir=terraform output -json
```

The outputs named `master_ip` and `worker_ips` currently contain complete server objects, rather than plain IP strings. Identify the public addresses from those objects or the cloud console and use them to populate the inventory. Terraform does not generate the inventory automatically.

State is local: no remote backend is configured. Protect the state and plan files, which can contain sensitive information. The generated `terraform/tfplan` path is not covered by the current `.gitignore`; do not commit it.

### 3. Bootstrap Kubernetes

```bash
cp ansible/inventory.ini.example ansible/inventory.ini
```

Replace the example addresses, SSH key path, and registry credentials. The playbook assumes an `ubuntu` user and an existing containerd installation from the golden image. Check that swap is disabled on the target nodes; the playbook does not disable it.

```bash
ansible all -i ansible/inventory.ini -m ping
ansible-playbook -i ansible/inventory.ini ansible/k8s-setup.yml
```

The playbook configures registry access, initializes kubeadm using an alternate image repository, installs Calico from a remote manifest, and joins the workers. It holds the installed Kubernetes packages, but does not pin an exact patch version.

It copies kubeconfig to `/home/ubuntu/.kube/config` on the control plane. Fetch it manually, substituting your SSH key and control-plane address:

```bash
mkdir -p "$HOME/.kube"
scp -i /path/to/ssh-key ubuntu@CONTROL_PLANE_IP:/home/ubuntu/.kube/config "$HOME/.kube/qwen-k8s-serve"
chmod 600 "$HOME/.kube/qwen-k8s-serve"
export KUBECONFIG="$HOME/.kube/qwen-k8s-serve"
kubectl get nodes -o wide
```

Confirm the kubeconfig server address is reachable from your workstation and, for automated deployment, from the GitHub Actions runner. Avoid storing kubeconfig in the repository; the current ignore rules do not exclude it.

### 4. Prepare cluster operators

Install a KubeRay operator version compatible with the committed Ray configuration. No chart version or values file is pinned in this repository; select and record the version you validate:

```bash
helm repo add kuberay https://ray-project.github.io/kuberay-helm/
helm repo update
# Set KUBERAY_CHART_VERSION to the version selected for your environment.
helm upgrade --install kuberay-operator kuberay/kuberay-operator \
  --namespace ray-system --create-namespace \
  --version "$KUBERAY_CHART_VERSION"
kubectl get crd rayservices.ray.io
```

The application YAML also contains a `ServiceMonitor`. Before applying the complete file, install Prometheus Operator's ServiceMonitor CRD and create the `monitoring` namespace. Prometheus/Grafana installation manifests and Helm values are not included. See [Monitoring](#monitoring) for selection requirements. Without these prerequisites, applying the complete YAML can fail after creating some resources.

### 5. Build and publish the runtime image

Use `endpoint/` as the Docker build context:

```bash
export IMAGE=YOUR_REGISTRY/qwen-vllm-serve:YOUR_UNIQUE_TAG
docker build -t "$IMAGE" endpoint/
docker push "$IMAGE"
```

Replace `asiyabani/qwen-vllm-serve:v2` in the application manifest with that image reference. Configure pull credentials separately if your registry is private.

The Dockerfile has overlapping dependency installation steps: it installs NumPy 2.2.6 and later overrides it with `numpy<2.0.0`. Its final environment is therefore not identical to `requirements.txt`, and some dependencies remain ranges. Validate a fresh build and model startup; a reproducible dependency lock is not supplied.

### 6. Pre-stage the model cache

On a machine with access to Hugging Face, create a cache with the standard Hugging Face layout:

```bash
python3 -m venv /tmp/qwen-model-download
/tmp/qwen-model-download/bin/pip install huggingface_hub
/tmp/qwen-model-download/bin/python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="Qwen/Qwen2.5-0.5B-Instruct",
    cache_dir="/tmp/qwen-model-cache",
)
PY
```

Copy the **contents** of `/tmp/qwen-model-cache/` into `/opt/models/hub/` on every Kubernetes node eligible to host the Ray head, preserving the `models--Qwen--Qwen2.5-0.5B-Instruct` directory, blobs, refs, and snapshot symlinks. Ensure the image's `ray` user can read the cache and access the mounted directory.

This distribution is manual. An empty `hostPath` directory will be created automatically if missing, but the model cannot load from that empty directory in offline mode. Model revision pinning and automated cache staging are not implemented.

### 7. Deploy and verify generation

```bash
kubectl apply -f kubernetes/vllm-deployment.yaml
kubectl -n default get rayservice qwen-vllm-service
kubectl -n default get pods -l app=qwen-vllm -o wide
kubectl -n default get svc qwen-vllm-serve
```

Inspect RayService status and container logs until the Serve deployment is healthy. For local verification without opening the NodePort externally, run this in a separate terminal:

```bash
kubectl -n default port-forward svc/qwen-vllm-serve 8000:8000
```

Then test both routing and inference:

```bash
export API_URL=http://127.0.0.1:8000
curl --fail-with-body "$API_URL/healthz"
curl --fail-with-body "$API_URL/generate" \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Explain Kubernetes in one sentence.","max_new_tokens":32}'
```

Alternatively, use `http://NODE_IP:30800` where network routing and firewall rules permit. No public hostname or HTTPS endpoint is provisioned by this repository.

## API usage

The FastAPI application exposes:

- `POST /generate`: simple text generation returning `{"text":"..."}`.
- `GET /v1/models`: the configured served model name and context limit.
- `POST /v1/chat/completions`: chat completions, optionally streamed using SSE.
- `POST /v1/completions`: text completions, optionally streamed using SSE.
- `GET /healthz`: a static `{"status":"ok"}` response.

There is no `/readyz` endpoint. `/healthz` does not run an inference or readiness check. Ray Serve separately calls the deployment's `check_health` method, which delegates to the engine's health check when available. Warmup runs lazily on the first generation request, so that request can take longer.

### Simple generation

```bash
curl --fail-with-body "$API_URL/generate" \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"What is an error budget?","max_new_tokens":64}'
```

`prompt` must contain 1–8000 characters by default. `max_new_tokens` defaults to 64 and accepts integers from 1 to 64. Input is formatted with the Qwen chat template before generation. The tokenized prompt, including template overhead, plus requested output must fit within the configured context limit (512 tokens in Kubernetes).

Schema validation failures return HTTP 422. A prompt exceeding the context budget returns HTTP 400.

### Chat completions and streaming

```bash
curl --fail-with-body "$API_URL/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{
    "model":"Qwen/Qwen2.5-0.5B-Instruct",
    "messages":[{"role":"user","content":"Give one tip for reducing MTTR."}],
    "max_tokens":64
  }'
```

For streaming, add `"stream":true` to the request and use `curl -N`. Streams end with `data: [DONE]`; `stream_options.include_usage` enables a final usage chunk.

### Text completions

```bash
curl --fail-with-body "$API_URL/v1/completions" \
  -H 'Content-Type: application/json' \
  -d '{
    "model":"Qwen/Qwen2.5-0.5B-Instruct",
    "prompt":"The three pillars of observability are",
    "max_tokens":32
  }'
```

Non-streamed text completions accept a string or a list of prompts. Streaming supports one prompt. Chat requests apply the chat template; text completions use the supplied prompt directly.

### Compatibility boundaries

The implementation supports common sampling fields, up to four output choices, and token usage reporting. Chat requests also accept `max_completion_tokens`. The output limit defaults to 64 tokens and can be changed for OpenAI-style routes with `OPENAI_MAX_TOKENS_LIMIT`.

This is a subset of the OpenAI API: unsupported extra fields, including tool-related options, are accepted and ignored. Message content handling extracts text only. Do not infer tool execution or multimodal support from schema acceptance. OpenAI-style validation and context errors return HTTP 400 with an `error` object; an unknown model returns HTTP 404. Authentication and per-client rate limiting are not implemented.

## Delivery workflow

[deploy.yml](.github/workflows/deploy.yml) runs when a push to `main` changes files under `kubernetes/`. It checks out the repository, writes the **raw kubeconfig YAML** from the `KUBECONFIG_DATA` GitHub repository secret to the runner's kubeconfig, installs Helm, and applies `kubernetes/vllm-deployment.yaml` with kubectl.

The workflow requires an already provisioned, reachable cluster with KubeRay and ServiceMonitor CRDs, the monitoring namespace, a populated model cache, and a published runtime image. Scope the kubeconfig permissions to the resources needed by this deployment.

There are no committed CI lint/test jobs, image build or push steps, vulnerability scans, rollout checks, smoke tests, or automatic rollback. A change only under `endpoint/` does not trigger deployment. Publish a new image and update the manifest image reference to deliver application changes. A successful `kubectl apply` does not prove that the model is serving requests.

## Monitoring

The application manifest includes `ray-service-monitor` in namespace `monitoring`, labeled `release: prometheus`. It selects Services labeled `app: qwen-vllm` in namespace `default` and requests `/metrics` from the named `metrics` and `serve` ports every 15 seconds.

Your Prometheus installation must select that ServiceMonitor and its namespace. The NodePort Service exposes the Ray metrics port at 8080. The FastAPI application does not define `/metrics` on its serving port; verify the port-8000 scrape target rather than assuming it provides engine metrics.

Prometheus/Grafana installation, persistent storage, dashboards, alert rules, SLOs, and complete vLLM metric coverage are not supplied as code. Verify scrape targets and emitted metric names in the running environment before describing monitoring as operational.

## Load testing

The included harness sends concurrent `/generate` requests with a fixed prompt using Bash, curl, and xargs:

```bash
cd load-test
cp env.example .env
# Edit .env: set URL to your own /generate endpoint and configure the test parameters.
bash load_test.sh
cd ..
```

Run it from `load-test/`, because it reads `.env` from the current directory. Set `URL`, `PROMPT`, `MAX_TOKENS`, `CONCURRENCY`, and `TOTAL_REQUESTS`. Replace the sample public URL before running. Start with low concurrency; the manifest permits two ongoing Serve requests while the engine is configured for one sequence.

The script prints response bodies, HTTP status codes, individual request durations, and total wall time. It does not calculate latency percentiles, output tokens per second, or enforce pass/fail thresholds. It interpolates the prompt into JSON without escaping, so use a simple prompt without embedded quotes or newlines. Concurrent script runs in the same directory share a temporary `payload.json` filename.

There are no k6 scenarios, randomized prompt corpus, retained benchmark results, or measured before/after comparisons in the repository. Performance claims require recording the image, model revision, hardware, runtime settings, workload, errors, and resource usage alongside results.

## Troubleshooting

- **RayService resource type is unknown:** verify KubeRay installation and `rayservices.ray.io` CRD availability.
- **ServiceMonitor apply fails:** check `servicemonitors.monitoring.coreos.com` and the `monitoring` namespace. Other resources in the same file may already have been created.
- **Pod remains Pending:** inspect `kubectl -n default describe pod POD_NAME` for CPU, memory, or scheduling constraints.
- **ImagePullBackOff:** check the manifest image reference, registry access, mirror availability, and pull credentials.
- **Model cannot be found offline:** check `/opt/models/hub` on the node hosting the Ray head, cache symlink integrity, and permissions.
- **Engine fails during startup:** inspect `kubectl -n default logs POD_NAME -c ray-head` for dependency, CPU extension, and memory errors. The Python module includes diagnostic probes for CPU extensions.
- **Health succeeds but generation is slow or fails:** test `/generate` directly, allow for first-request warmup, and inspect logs. A static health response does not validate inference.
- **Context-length error:** shorten the prompt or reduce requested output; chat-template tokens count toward the 512-token budget.
- **GitHub deployment cannot connect:** verify the kubeconfig server address, certificate configuration, permissions, and runner network access.

## Security and limitations

The current files have several constraints to address before exposing the service broadly:

- The golden-image configuration contains a fixed password and enables password SSH. Remove build credentials from the final image and rotate them wherever that image was used.
- The example Ansible inventory disables SSH host-key checking. Configure trusted host keys for a maintained environment. Registry credentials are copied to node configuration, and their handling is not protected with `no_log` in the playbook.
- Terraform enables public IPv4, uses existing security groups, and defines no private network. Firewall restrictions are an external responsibility.
- NodePort exposes both serving and metrics ports. The API has no authentication, TLS, or rate limiting, and no NetworkPolicies are committed. Restrict access, including metrics and Ray management interfaces.
- The runtime uses the `ray` user, but the Dockerfile grants world-write permissions on `/models`; the manifest does not define a hardened Pod security context.
- Secret scanning, image scanning, dedicated reviewer RBAC, and an access handover document are not included. Share credentials outside Git and use limited permissions.
- Terraform state, local configuration, inventories, and model caches must remain private. Existing ignore rules cover several of these, but do not cover every sensitive or generated file.
- Dependencies, model revisions, and operator versions are not fully locked. Cache distribution, image publication, and cluster add-on installation remain manual.

## Teardown

Remove application resources while the cluster is reachable:

```bash
kubectl delete -f kubernetes/vllm-deployment.yaml
```

This does not remove node-local model files or separately installed operators and monitoring tools. Uninstall shared components only if they are dedicated to this project.

To delete the VMs managed by this Terraform state, review and apply a destroy plan:

```bash
terraform -chdir=terraform plan -destroy -out=destroy.tfplan
terraform -chdir=terraform apply destroy.tfplan
```

VM deletion removes their local model caches. Protect and remove generated plan files after use; they are not excluded by the current ignore rules. Terraform does not delete the separately uploaded custom image, existing SSH key, or existing security group.

## AI usage and license

AI assistance and the author's engineering workflow are described in [docs/ai-usage.md](docs/ai-usage.md).

Author: **Mohammad Sajjad Asiyabani**. Prepared for the **ArvanCloud SRE Technical Challenge**.

Distributed under the [Apache License 2.0](LICENSE).
