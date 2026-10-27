# AI Usage Report

This document describes how I used AI while completing the ArvanCloud SRE technical challenge. The percentages below are my approximate estimates of AI involvement in producing and refining each part of the project. They are not measured percentages of generated lines, development time, or project-wide contribution.

I used **Cursor, OpenCode, Gemini, and ChatGPT** for different tasks. My use ranged from occasional troubleshooting and code review to generating the model-serving application. I made the project decisions, reviewed and adjusted the output, and performed testing myself.

## Usage by project component

### Packer and golden image — approximately 10%

I designed and implemented the golden-image build myself, using Packer documentation and community resources. Gemini provided limited help with minor bugs after the initial implementation. AI was used for troubleshooting rather than generating the image-building configuration or provisioning scripts.

### Terraform — approximately 5%

I wrote the Terraform configuration myself, consulting Terraform documentation and ArvanCloud's documentation and repositories on its website, GitHub, and GitLab. I used AI to review the code structure against best practices. This review was advisory; it does not imply that every recommended practice was implemented.

### Ansible and Kubernetes cluster bootstrap — 0%

I wrote the Ansible configuration and carried out the cluster setup myself without AI assistance. This covers node configuration and Kubernetes cluster bootstrap, separately from the application manifests described below.

### Dockerfile — 0%

I wrote the Dockerfile myself without AI assistance.

### Model-serving APIs and `serve_script.py` — approximately 100%

I used Cursor and OpenCode to generate and develop the model-serving application and its API implementation. I chose this approach to manage the time available for the challenge. This was the component with the most extensive AI involvement in code production.

My contribution included reviewing the generated implementation, testing it, and investigating failures during integration and deployment.

### Kubernetes application manifests and Ray configuration — approximately 70%

I used ChatGPT to prepare prompts and OpenCode to generate code for the Kubernetes application manifests and Ray configuration. I had limited experience with Ray and used AI to reduce the time needed to work through its documentation during the challenge.

I reviewed and adjusted the generated configuration and tested the deployment myself. This estimate concerns the model-serving deployment, rather than the cluster bootstrap, which I implemented without AI.

### GitHub Actions — 0%

I wrote the GitHub Actions deployment workflow myself without AI assistance.

### Monitoring — approximately 30%

I used Gemini to help locate Ray metrics quickly and assist with dashboard preparation. I performed the remaining monitoring work myself.

This describes my monitoring work during the challenge. The repository currently contains a ServiceMonitor, but does not include dashboard definitions or the monitoring stack installation configuration. Dashboard preparation should therefore not be interpreted as a reproducible dashboard setup delivered in this repository.

### Load-test script — 0%

I wrote the load-test script myself without AI assistance.

### Documentation — approximately 99%

I used ChatGPT to draft and structure the project documentation, including the README and this disclosure, and reviewed and corrected the resulting text myself. AI was also used to create an earlier planning document that has since been removed.

The README was subsequently reviewed against the repository and rewritten with AI assistance to distinguish the committed implementation from planned capabilities and manual prerequisites. This report was updated from my descriptions of the tools, tasks, and approximate involvement in each component.

## Troubleshooting and validation

AI mainly helped me analyze errors and identify where to investigate next. For example, I encountered numerous errors while bringing up the model on the Ray cluster. AI helped me understand the likely source of those errors and identify the topics or documentation I needed to read to resolve them.

I performed the testing myself. AI-assisted diagnosis and code generation were inputs to that process, rather than evidence that a change worked. This report does not claim exhaustive test coverage, automated validation of every generated change, or an independently verified rebuild of the complete system.

## Representative prompt

The following is an illustrative example of the format I used, rather than a verbatim conversation transcript. Other prompts generally followed a similar structure: a role, the challenge context, the requirements, and the requested output.

```prompt
 Act as a Senior MLOps/Software Engineer. I am deploying the `Qwen/Qwen2.5-0.5B-Instruct` model on CPU using **Ray Serve**, **vLLM**, and **FastAPI** inside a Kubernetes cluster.

I need you to write the complete Python script (`serve_script.py`) that will be served via Ray Serve. The script must initialize the vLLM `AsyncLLMEngine` for CPU-only execution and expose the following two endpoints through the FastAPI app:

1. **Custom Endpoint:** `POST /generate`
   - Accepts a JSON payload containing `prompt` (string) and `max_new_tokens` (integer, maximum 64).
   - Returns a JSON response strictly in this format: `{"text": "generated_output_here"}`.

2. **OpenAI-Compatible Endpoint:** `POST /v1/chat/completions` (or `/v1/completions`)
   - Fully compatible with the standard OpenAI API request/response format.
   - It should properly route requests to the underlying vLLM async engine.

Constraints:
- Engine args must be optimized for CPU: `device="cpu"`, `enforce_eager=True`, `dtype="float32"`, `gpu_memory_utilization=0.0`.
- The code must be production-ready and structured so I can directly paste it into a Kubernetes ConfigMap for my `RayService` deployment.
- Please output only the clean Python code with necessary imports and brief comments.a
```

The requirements mentioned in a prompt describe the requested scope; they do not establish that every capability was implemented or validated. The current README documents the repository's implementation and limitations.
