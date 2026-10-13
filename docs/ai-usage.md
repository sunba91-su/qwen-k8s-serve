# AI Usage Report

## 1. Overview
Throughout the ArvanCloud AIOps technical challenge, Artificial Intelligence (AI) was utilized as a **Pair-Programming Assistant**. The primary goal of using AI was to accelerate the generation of boilerplate code and structure the project documentation. 

I maintained strict oversight over all architectural decisions. While AI was consulted for hints during troubleshooting, the actual debugging, source code review, and resolution of critical infrastructure issues were performed manually to ensure a deep understanding of the deployed environment.

**Tools Utilized:**
- Large Language Models (LLMs): Gemini / ChatGPT / Claude

---

## 2. Breakdown of AI Usage by Project Phase

### Phase 1: Infrastructure as Code (Terraform & Packer)
- **AI Usage:** Low (~10%)
- **How AI was used:**
  - Consulting on the best practices for structuring `.gitignore` and `.tfvars` to prevent secret leakage.
- **Human Contribution (Manual Engineering):**
  - **Initialization:** Generating the initial boilerplate code and folder structure for Terraform and Packer.
  - **Debugging & Troubleshooting:** When facing issues with the ArvanCloud Terraform provider (e.g., the `404 Requested plan not found` error and provider registry resolution issues), I manually reviewed the official Terraform registry documentation and the provider's source code.
  - **Code Refactoring:** Manually updated deprecated resource names (from `arvan_iaas_instance` to `arvancloud_iaas_server`) and handled the complex output schema changes directly based on the official documentation, without relying on AI-generated fixes.

### Phase 2: Configuration Management & Cluster Setup
- **AI Usage:** Low (~5%)
- **How AI was used:**
  - Review my Ansible playbook and Ansible Tasks to stay on the best practice
- **Human Contribution (Manual Engineering):**
  - Generating basic Ansible tasks for installing required packages (`kubelet`, `kubeadm`, `kubectl`).

### Phase 6: Project Documentation
- **AI Usage:** Very High (~99%)
- **How AI was used:**
  - Generating the `ROADMAP.md` to track progress efficiently.
  - Structuring and writing the comprehensive `README.md` in a professional English format, including the architecture overview, prerequisites, and quick-start guides.
  - Formatting this very `ai-usage.md` report based on my exact inputs and engineering workflow.

---

## 3. Sample Prompts Used
To demonstrate the interaction with the AI assistant, here is an example of a prompt used for generating the project documentation:

> "Act as a Senior Site Reliability Engineer (SRE) and Technical Writer. I am working on a technical challenge for an SRE position at ArvanCloud. Please generate a detailed ROADMAP.md and a professional README.md for my GitHub repository based on the following requirements: 3-node Kubernetes cluster, KubeRay, vLLM Qwen model, and Prometheus/Grafana monitoring..."

---

## 4. Conclusion
Leveraging AI for boilerplate generation and documentation allowed me to strictly focus my time and engineering effort on the core SRE tasks: designing a resilient architecture, ensuring secure secret management, and manually debugging infrastructure-level provider issues. No code was committed without a full understanding of its execution logic and state.