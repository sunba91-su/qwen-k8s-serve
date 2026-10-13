# Roadmap — AIOps Text Generation Cloud Service

Execution plan for the ArvanCloud SRE technical challenge. The work is split into eight phases
that map onto a one-week delivery window. Each phase ends with an explicit **exit criterion**
so progress is verifiable rather than estimated.

**Legend:** `- [ ]` pending · `- [x]` done · 🔴 must-have (challenge requirement) · 🟡 should-have · 🟢 nice-to-have

---

## Timeline at a Glance

| Day | Phase(s) | Milestone |
|-----|----------|-----------|
| Day 1 | 0, 1 | Repository bootstrapped, 3 VMs provisioned by Terraform |
| Day 2 | 2 | 3-node Kubernetes cluster bootstrapped by Ansible |
| Day 3 | 3 | KubeRay + vLLM + Ray Serve running Qwen2.5-0.5B on CPU |
| Day 4 | 4, 5 | `/generate` and OpenAI-compatible API live; CI/CD pipeline green |
| Day 5 | 6 | Prometheus + Grafana dashboards for cluster and AI workload |
| Day 6 | 7 | Baseline load test, optimization, after-benchmark |
| Day 7 | 8 | Documentation, access handover, final review, buffer |

---

## Phase 0 — Project Bootstrap (Day 1, morning)

- [ ] Define the repository layout:
  ```
  infrastructure/        # VM, network, firewall, SSH key provisioning
  ansible/          # OS hardening, container runtime, kubeadm bootstrap
  k8s/              # Kubernetes manifests & Helm values (kustomize overlays)
  serve/            # Ray Serve application (vLLM engine + FastAPI ingress)
  docker/           # Container image for the Ray/vLLM CPU runtime
  monitoring/       # Prometheus rules, ServiceMonitors, Grafana dashboards
  loadtest/         # k6 / Locust scenarios and prompt corpus
  benchmarks/       # Raw results and before/after reports
  .github/workflows # CI/CD pipelines
  docs/             # Architecture, runbooks, access guide
  ```
- [x] 🔴 Add `.gitignore` entries for `*.tfstate*`, `.terraform/`, `kubeconfig*`, `*.pem`, `.venv/`
- [ ] 🟡 Add `pre-commit` hooks: `terraform fmt`, `tflint`, `ansible-lint`, `yamllint`, `ruff`, `kubeconform`
- [ ] 🟡 Add a top-level `Makefile` as the single entry point (`make infra`, `make cluster`, `make deploy`, `make loadtest`, `make destroy`)
- [ ] 🔴 Start `ai-usage.md` immediately and update it continuously (do not reconstruct it at the end)
- [x] Choose and document sizing for the 3 nodes (e.g. 1× control-plane 4 vCPU/8 GiB, 2× workers 8 vCPU/16 GiB)

**Exit criterion:** repository skeleton committed, tooling versions pinned in `docs/versions.md`.

---

## Phase 1 — Infrastructure Provisioning with IaC (Day 1)

- [x] 🔴 Configure the Terraform provider for the target cloud (ArvanCloud IaaS, or an equivalent provider) with credentials supplied via environment variables only
- [x] 🔴 Configure a remote/locked Terraform state backend (S3-compatible object storage) or document why local state is acceptable
- [x] 🔴 Provision 3 virtual machines via a reusable `modules/node` module
  - [x] `k8s-cp-01` — control plane
  - [x] `k8s-worker-01` — Ray head + platform services (monitoring, ingress)
  - [x] `k8s-worker-02` — Ray worker dedicated to vLLM inference
- [x] 🔴 Provision private network, security groups/firewall rules (22, 6443, 80/443, NodePort range restricted, intra-cluster traffic)
- [x] 🔴 Inject SSH public key; disable password authentication
- [x] 🔴 Output node IPs and auto-generate the Ansible inventory (`templatefile` → `ansible/inventory/hosts.ini`)
- [ ] 🟡 Tag/label all resources (`project=qwen-k8s-serve`, `owner`, `env`)
- [ ] 🟡 Validate idempotency: `terraform plan` after `apply` shows no changes

**Exit criterion:** `terraform apply` creates all 3 nodes from zero; `ansible all -m ping` succeeds.

---

## Phase 2 — Kubernetes Cluster Setup (Day 2)

### 2.1 Node preparation (Ansible role `common`)
- [x] 🔴 OS baseline: package updates, time sync (chrony), swap disabled, kernel modules (`overlay`, `br_netfilter`), sysctl tuning
- [x] 🔴 Install and configure `containerd` with `SystemdCgroup = true`
- [x] 🔴 Install pinned `kubeadm`, `kubelet`, `kubectl` versions and hold packages
- [ ] 🟡 Basic hardening: UFW/firewalld, fail2ban, unattended security updates

### 2.2 Cluster bootstrap (Ansible roles `control_plane`, `worker`)
- [x] 🔴 `kubeadm init` on the control plane with a versioned `ClusterConfiguration`
- [x] 🔴 Join both workers using a generated, short-lived join token
- [x] 🔴 Install CNI (Calico or Cilium) via Helm
- [x] 🔴 Fetch `admin.conf` to the operator workstation as `kubeconfig` (never committed)
- [ ] 🟡 Enable kubelet `cpuManagerPolicy: static` and reserved CPUs on the inference node (prerequisite for Guaranteed-QoS pinning in Phase 7)

### 2.3 Cluster add-ons
- [ ] 🔴 Ingress controller (ingress-nginx) or Gateway API implementation
- [ ] 🔴 Storage: `local-path-provisioner` (default StorageClass) for model cache and Prometheus TSDB
- [ ] 🔴 `metrics-server`
- [ ] 🟡 cert-manager + Let's Encrypt for TLS on the public endpoint
- [ ] 🟡 Node labels and taints: `workload=inference:NoSchedule` on `k8s-worker-02`

**Exit criterion:** `kubectl get nodes` shows 3 `Ready` nodes; a test pod is reachable through Ingress. The whole phase runs end-to-end from a single `ansible-playbook site.yml`.

---

## Phase 3 — AI Model Deployment: KubeRay + vLLM + Ray Serve (Day 3)

### 3.1 Runtime image
- [ ] 🔴 Build a CPU-only image: Ray base + vLLM CPU backend (built with `VLLM_TARGET_DEVICE=cpu`), pinned versions, non-root user
- [ ] 🔴 Verify CPU instruction support on nodes (`lscpu | grep -E 'avx512|avx2'`) and choose the matching build
- [ ] 🔴 Push to a container registry (GHCR / ArvanCloud Container Registry) with immutable tags (git SHA)
- [ ] 🟡 Multi-stage build to minimize image size; scan with Trivy

### 3.2 KubeRay operator
- [ ] 🔴 Install the KubeRay operator via Helm into the `ray-system` namespace with pinned chart version
- [ ] 🔴 Verify CRDs: `RayCluster`, `RayService`, `RayJob`

### 3.3 Model serving
- [ ] 🔴 Pre-download `Qwen/Qwen2.5-0.5B-Instruct` to a PVC (init container or one-off Job) to avoid cold-start downloads from Hugging Face
- [ ] 🔴 Author a `RayService` manifest:
  - [ ] Ray head on `k8s-worker-01` with `num-cpus: 0` (no inference work on the head)
  - [ ] One Ray worker group on `k8s-worker-02` (tolerates the inference taint)
  - [ ] Serve application with **1 replica** of the vLLM deployment
  - [ ] Explicit CPU/memory `requests` and `limits`
- [ ] 🔴 Configure vLLM for CPU: `device=cpu`, `dtype=bfloat16`, `VLLM_CPU_KVCACHE_SPACE`, `VLLM_CPU_OMP_THREADS_BIND`, `max_model_len`
- [ ] 🔴 Readiness/liveness probes and a sane `serviceUnhealthySecondThreshold`
- [ ] 🟡 Zero-downtime upgrades validated via `RayService` blue/green rollout

**Exit criterion:** `RayService` status is `Running`, the Serve deployment is `HEALTHY`, and a test prompt returns generated text from inside the cluster.

---

## Phase 4 — API Development (Day 4, morning)

- [ ] 🔴 FastAPI ingress deployment wrapping the vLLM `AsyncLLMEngine`
- [ ] 🔴 `POST /generate`
  - [ ] Request schema: `prompt: str` (non-empty, bounded length), `max_new_tokens: int` (1–64, default 64)
  - [ ] Response schema: `{"text": "<generated text>"}`
  - [ ] `422` on validation errors (e.g. `max_new_tokens > 64`)
  - [ ] Apply the Qwen chat template to the prompt
- [ ] 🔴 OpenAI-compatible endpoints
  - [ ] `GET /v1/models`
  - [ ] `POST /v1/chat/completions` (including `stream: true` via SSE)
  - [ ] `POST /v1/completions`
- [ ] 🔴 `GET /healthz` (liveness) and `GET /readyz` (engine loaded)
- [ ] 🔴 Expose through Ingress with a stable hostname
- [ ] 🟡 Structured JSON logging with request ID, prompt token count, generated token count, latency
- [ ] 🟡 Request timeout and back-pressure via Ray Serve `max_ongoing_requests` / `max_queued_requests` (return `503` instead of unbounded queueing)
- [ ] 🟡 Unit tests (`pytest`) for request validation and response schemas
- [ ] 🟢 API key authentication and per-client rate limiting at the Ingress
- [ ] 🟢 Verify compatibility using the official `openai` Python SDK

**Exit criterion:** `curl` examples from the README succeed against the public endpoint; validation errors behave as specified.

---

## Phase 5 — CI/CD Pipelines (Day 4, afternoon)

- [ ] 🔴 **CI — on every pull request**
  - [ ] `terraform fmt -check`, `terraform validate`, `tflint`
  - [ ] `ansible-lint`, `yamllint`
  - [ ] `kubeconform` against rendered manifests (`kustomize build` / `helm template`)
  - [ ] `ruff` + `pytest` for the Serve application
  - [ ] Docker build (no push) + Trivy vulnerability scan
- [ ] 🔴 **CD — on merge to `main`**
  - [ ] Build and push image tagged with the commit SHA
  - [ ] Update the image tag in the `RayService` manifest
  - [ ] Deploy to the cluster (kubeconfig stored as an encrypted CI secret, least-privilege ServiceAccount)
  - [ ] Post-deploy smoke test hitting `/generate` and `/v1/chat/completions`
  - [ ] Automatic rollback (or failed-job alert) if the smoke test fails
- [ ] 🟡 **Infra pipeline** — `terraform plan` on PR (posted as comment), manual-approval `apply`
- [ ] 🟢 GitOps alternative: Argo CD watching `k8s/` instead of push-based deploys

**Exit criterion:** a code change merged to `main` reaches the cluster without manual steps and is verified by the smoke test.

---

## Phase 6 — Monitoring & Observability (Day 5)

- [ ] 🔴 Install `kube-prometheus-stack` (Prometheus Operator, Prometheus, Alertmanager, Grafana, node-exporter, kube-state-metrics) — or VictoriaMetrics k8s-stack as an alternative
- [ ] 🔴 Persistent storage and a retention policy for the TSDB
- [ ] 🔴 Scrape Ray metrics: `PodMonitor` for Ray head/worker metrics port (8080) and Serve metrics
- [ ] 🔴 Scrape vLLM engine metrics (`vllm:*` — TTFT, time-per-output-token, running/waiting requests, KV-cache usage, generated tokens)
- [ ] 🔴 Grafana dashboards (provisioned as code from `monitoring/dashboards/*.json`):
  - [ ] **Cluster** — node CPU/memory/disk/network, pod restarts, resource requests vs. usage
  - [ ] **Ray** — cluster resources, Serve replica health, request rate, Serve latency, errors
  - [ ] **LLM / vLLM** — tokens/s, TTFT p50/p95/p99, inter-token latency, queue depth, KV-cache utilization
  - [ ] **API SLO** — availability, error rate, latency vs. target, error budget burn
- [ ] 🟡 Define SLOs (e.g. 99% availability, p95 `/generate` latency target derived from the baseline)
- [ ] 🟡 Alerting rules: Serve replica unhealthy, high 5xx rate, p95 latency breach, node memory pressure, pod `OOMKilled`
- [ ] 🟢 Centralized logs (Loki + Promtail) linked from Grafana

**Exit criterion:** all dashboards render live data during a test request burst; at least one alert fires correctly in a deliberate failure test.

---

## Phase 7 — Load Testing, Optimization & Benchmarking (Day 6)

### 7.1 Test harness
- [ ] 🔴 Build a random prompt corpus (varying lengths and topics) in `loadtest/prompts.json`
- [ ] 🔴 k6 (or Locust) scenarios with random prompt selection and random `max_new_tokens` (1–64):
  - [ ] Smoke — 1 VU, sanity check
  - [ ] Load — ramp to expected concurrency, sustained for 5–10 min
  - [ ] Stress — ramp until error rate or latency breaches the SLO (find the knee)
  - [ ] Soak (🟢) — moderate load for 30+ minutes to detect leaks
- [ ] 🔴 Record: RPS, p50/p95/p99 latency, TTFT, output tokens/s, error rate, CPU/memory per pod and node

### 7.2 Baseline ("before")
- [ ] 🔴 Run the suite on the default, untuned configuration
- [ ] 🔴 Export results to `benchmarks/before/` and snapshot Grafana panels

### 7.3 Optimization
- [ ] 🔴 Right-size CPU/memory requests and limits using observed usage
- [ ] 🔴 Tune vLLM CPU parameters: `VLLM_CPU_KVCACHE_SPACE`, `VLLM_CPU_OMP_THREADS_BIND`, `max_num_seqs`, `max_num_batched_tokens`, `max_model_len`
- [ ] 🔴 Tune Ray Serve: `max_ongoing_requests`, request timeouts, head node `num-cpus: 0`
- [ ] 🟡 Guaranteed QoS (requests == limits, integer CPUs) + static CPU manager for core pinning
- [ ] 🟡 Isolate inference from noisy neighbours (taints/tolerations, node affinity)
- [ ] 🟢 Evaluate alternative dtypes/quantization and their quality/latency trade-off
- [ ] Change **one variable at a time** and log each experiment in `benchmarks/experiments.md`

### 7.4 After-benchmark
- [ ] 🔴 Re-run the identical suite on the tuned configuration → `benchmarks/after/`
- [ ] 🔴 Publish a before/after comparison table with analysis in `benchmarks/REPORT.md`

**Exit criterion:** a reproducible, documented performance improvement (or a justified explanation of the limiting factor) backed by raw data.

---

## Phase 8 — Documentation & Handover (Day 7)

- [ ] 🔴 `README.md` — final architecture, quick start, API usage, monitoring, benchmark summary
- [ ] 🔴 `ai-usage.md` — which AI tools were used, for what, representative prompts, and what was manually verified or corrected
- [ ] 🔴 `docs/access.md` — how reviewers obtain kubeconfig and SSH access (credentials shared out-of-band, never committed)
- [ ] 🔴 Create a read-only reviewer kubeconfig (dedicated ServiceAccount + RBAC) and a time-limited SSH key
- [ ] 🟡 `docs/architecture.md` — design decisions and trade-offs (why kubeadm, why CPU tuning choices, etc.)
- [ ] 🟡 `docs/runbook.md` — common failures and remediation (Serve replica unhealthy, OOMKilled, node NotReady)
- [ ] 🟡 Full teardown and rebuild from scratch to prove reproducibility (`make destroy && make all`)
- [ ] 🔴 Final review: secrets scan (`gitleaks`), links checked, all pipelines green, tagged release `v1.0.0`

**Exit criterion:** a reviewer can understand, access, and reproduce the entire system using only the repository and the shared credentials.

---

## Definition of Done (Challenge Requirements Checklist)

- [ ] 3-node Kubernetes cluster provisioned and configured entirely by IaC
- [ ] KubeRay, vLLM, and Ray Serve running on CPU-only nodes
- [ ] `Qwen/Qwen2.5-0.5B-Instruct` served with exactly 1 replica
- [ ] `POST /generate` (`prompt`, `max_new_tokens` ≤ 64) returns JSON with a `text` field
- [ ] OpenAI-compatible endpoint available
- [ ] Prometheus/VictoriaMetrics + Grafana dashboards for cluster and AI workload metrics
- [ ] Load tests with random prompts, resource optimization, before/after benchmarks
- [ ] IaC code, Kubernetes manifests, CI/CD pipelines committed
- [ ] Kubeconfig / SSH access provided to reviewers
- [ ] `ai-usage.md` committed
