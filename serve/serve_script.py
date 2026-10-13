"""Ray Serve application: Qwen2.5-0.5B-Instruct on vLLM (CPU) behind FastAPI.

Endpoints:
    POST /generate              {"prompt": str, "max_new_tokens": 1..64} -> {"text": str}
    GET  /v1/models             OpenAI-compatible model listing
    POST /v1/chat/completions   OpenAI-compatible chat completions (supports stream=true)
    POST /v1/completions        OpenAI-compatible text completions (supports stream=true)
    GET  /healthz               Liveness

RayService serveConfigV2 import_path: serve_script:deployment
(mount the ConfigMap into head and worker pods and add the mount path to PYTHONPATH).
"""

import asyncio
import dataclasses
import json
import logging
import os
import time
import uuid
from typing import Any, AsyncIterator, Literal

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from ray import serve
from transformers import AutoTokenizer
from vllm import AsyncEngineArgs, AsyncLLMEngine, SamplingParams
from vllm.outputs import RequestOutput

logger = logging.getLogger("ray.serve")

# --------------------------------------------------------------------------------------
# Configuration (override through RayService runtime_env.env_vars)
# --------------------------------------------------------------------------------------
MODEL_ID = os.getenv("MODEL_ID", "Qwen/Qwen2.5-0.5B-Instruct")
SERVED_MODEL_NAME = os.getenv("SERVED_MODEL_NAME", MODEL_ID)
MODEL_CACHE_DIR = os.getenv("MODEL_CACHE_DIR") or None  # e.g. /models (PVC)

MAX_NEW_TOKENS_LIMIT = 64
OPENAI_MAX_TOKENS_LIMIT = int(os.getenv("OPENAI_MAX_TOKENS_LIMIT", str(MAX_NEW_TOKENS_LIMIT)))
MAX_PROMPT_CHARS = int(os.getenv("MAX_PROMPT_CHARS", "8000"))

MAX_MODEL_LEN = int(os.getenv("MAX_MODEL_LEN", "2048"))
MAX_NUM_SEQS = int(os.getenv("MAX_NUM_SEQS", "16"))
VLLM_DTYPE = os.getenv("VLLM_DTYPE", "float32")
# Ignored by the CPU backend (KV cache size comes from VLLM_CPU_KVCACHE_SPACE, in GiB).
# Some vLLM releases validate this as > 0; set the env var to e.g. 0.9 if 0.0 is rejected.
VLLM_GPU_MEMORY_UTILIZATION = float(os.getenv("VLLM_GPU_MEMORY_UTILIZATION", "0.0"))

# Ray exports OMP_NUM_THREADS=num_cpus to the replica, which drives vLLM's CPU threading.
REPLICA_NUM_CPUS = float(os.getenv("REPLICA_NUM_CPUS", "6"))
MAX_ONGOING_REQUESTS = int(os.getenv("MAX_ONGOING_REQUESTS", "32"))

# Qwen2.5 recommended sampling defaults for the /generate endpoint.
GENERATE_TEMPERATURE = float(os.getenv("GENERATE_TEMPERATURE", "0.7"))
GENERATE_TOP_P = float(os.getenv("GENERATE_TOP_P", "0.8"))
GENERATE_REPETITION_PENALTY = float(os.getenv("GENERATE_REPETITION_PENALTY", "1.05"))


def build_engine_args() -> AsyncEngineArgs:
    candidate: dict[str, Any] = {
        "model": MODEL_ID,
        "served_model_name": SERVED_MODEL_NAME,
        "download_dir": MODEL_CACHE_DIR,
        "device": "cpu",
        "dtype": VLLM_DTYPE,
        "enforce_eager": True,
        "gpu_memory_utilization": VLLM_GPU_MEMORY_UTILIZATION,
        "max_model_len": MAX_MODEL_LEN,
        "max_num_seqs": MAX_NUM_SEQS,
        "tensor_parallel_size": 1,
        "trust_remote_code": False,
        "disable_log_stats": False,
    }
    # Newer vLLM releases removed some args (e.g. `device`, auto-detected from the build).
    supported = {f.name for f in dataclasses.fields(AsyncEngineArgs)}
    dropped = sorted(set(candidate) - supported)
    if dropped:
        logger.warning("Engine args not supported by this vLLM version, skipped: %s", dropped)
    return AsyncEngineArgs(**{k: v for k, v in candidate.items() if k in supported})


# --------------------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------------------
class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=MAX_PROMPT_CHARS)
    max_new_tokens: int = Field(MAX_NEW_TOKENS_LIMIT, ge=1, le=MAX_NEW_TOKENS_LIMIT)


class GenerateResponse(BaseModel):
    text: str


class StreamOptions(BaseModel):
    include_usage: bool = False


class OpenAISamplingRequest(BaseModel):
    # Unsupported optional OpenAI fields (logit_bias, tools, ...) are accepted and ignored.
    model_config = ConfigDict(extra="ignore")

    model: str | None = None
    max_tokens: int | None = Field(None, ge=1)
    temperature: float = Field(1.0, ge=0.0, le=2.0)
    top_p: float = Field(1.0, gt=0.0, le=1.0)
    n: int = Field(1, ge=1, le=4)
    stop: str | list[str] | None = None
    presence_penalty: float = Field(0.0, ge=-2.0, le=2.0)
    frequency_penalty: float = Field(0.0, ge=-2.0, le=2.0)
    seed: int | None = None
    stream: bool = False
    stream_options: StreamOptions | None = None
    user: str | None = None


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: Literal["system", "developer", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]] | None = None


class ChatCompletionRequest(OpenAISamplingRequest):
    messages: list[ChatMessage] = Field(..., min_length=1)
    max_completion_tokens: int | None = Field(None, ge=1)


class CompletionRequest(OpenAISamplingRequest):
    prompt: str | list[str]


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
class PromptTooLongError(ValueError):
    pass


def openai_error(
    status: int,
    message: str,
    err_type: str = "invalid_request_error",
    param: str | None = None,
    code: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": err_type, "param": param, "code": code}},
    )


def sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def message_text(content: str | list[dict[str, Any]] | None) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") for part in content if part.get("type") == "text")


def usage(outputs: list[RequestOutput]) -> dict[str, int]:
    prompt_tokens = sum(len(o.prompt_token_ids or []) for o in outputs)
    completion_tokens = sum(len(c.token_ids) for o in outputs for c in o.outputs)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


# --------------------------------------------------------------------------------------
# FastAPI app + Ray Serve deployment
# --------------------------------------------------------------------------------------
app = FastAPI(title="qwen-k8s-serve", version="1.0.0")


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # OpenAI clients expect 400 + {"error": {...}}; /generate keeps FastAPI's standard 422.
    if request.url.path.startswith("/v1/"):
        first = exc.errors()[0] if exc.errors() else {}
        param = ".".join(str(p) for p in first.get("loc", ())[1:]) or None
        return openai_error(400, first.get("msg", "Invalid request"), param=param)
    return await request_validation_exception_handler(request, exc)


@serve.deployment(
    name="qwen-vllm",
    num_replicas=1,
    max_ongoing_requests=MAX_ONGOING_REQUESTS,
    ray_actor_options={"num_cpus": REPLICA_NUM_CPUS},
    health_check_period_s=10,
    health_check_timeout_s=30,
    graceful_shutdown_timeout_s=30,
)
@serve.ingress(app)
class QwenVLLMDeployment:
    def __init__(self) -> None:
        self.created = int(time.time())
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, cache_dir=MODEL_CACHE_DIR)
        self.stop_token_ids = sorted(
            {
                tid
                for tok in ("<|im_end|>", "<|endoftext|>")
                if (tid := self.tokenizer.convert_tokens_to_ids(tok)) is not None
                and tid != self.tokenizer.unk_token_id
            }
        )
        self.engine = AsyncLLMEngine.from_engine_args(build_engine_args())
        logger.info("vLLM engine ready: model=%s dtype=%s device=cpu", MODEL_ID, VLLM_DTYPE)

    async def check_health(self) -> None:
        # Called by Ray Serve; raising marks the replica unhealthy and triggers a restart.
        await self.engine.check_health()

    # ---------------------------------------------------------------- engine plumbing
    def _chat_prompt(self, messages: list[dict[str, str]]) -> str:
        return self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

    def _check_prompt_length(self, prompt: str, max_tokens: int) -> None:
        n_tokens = len(self.tokenizer.encode(prompt, add_special_tokens=False))
        if n_tokens + max_tokens > MAX_MODEL_LEN:
            raise PromptTooLongError(
                f"Prompt is {n_tokens} tokens; prompt + max_tokens ({max_tokens}) "
                f"exceeds the model context length of {MAX_MODEL_LEN}."
            )

    async def _stream(
        self, prompt: str, params: SamplingParams, request_id: str
    ) -> AsyncIterator[RequestOutput]:
        finished = False
        try:
            async for output in self.engine.generate(prompt, params, request_id):
                finished = output.finished
                yield output
        finally:
            # Client disconnect or cancellation: free the sequence slot in the engine.
            if not finished:
                await self.engine.abort(request_id)

    async def _complete(self, prompt: str, params: SamplingParams, request_id: str) -> RequestOutput:
        final: RequestOutput | None = None
        async for output in self._stream(prompt, params, request_id):
            final = output
        if final is None:
            raise RuntimeError("Engine returned no output")
        return final

    def _openai_sampling_params(self, req: OpenAISamplingRequest, max_tokens: int) -> SamplingParams:
        stop = [req.stop] if isinstance(req.stop, str) else req.stop
        return SamplingParams(
            n=req.n,
            temperature=req.temperature,
            top_p=req.top_p,
            max_tokens=max_tokens,
            stop=stop,
            stop_token_ids=self.stop_token_ids,
            presence_penalty=req.presence_penalty,
            frequency_penalty=req.frequency_penalty,
            seed=req.seed,
        )

    @staticmethod
    def _model_error(model: str | None) -> JSONResponse | None:
        if model and model not in (SERVED_MODEL_NAME, MODEL_ID):
            return openai_error(
                404, f"The model '{model}' does not exist.", param="model", code="model_not_found"
            )
        return None

    @staticmethod
    def _resolve_max_tokens(requested: int | None) -> int | JSONResponse:
        if requested is None:
            return OPENAI_MAX_TOKENS_LIMIT
        if requested > OPENAI_MAX_TOKENS_LIMIT:
            return openai_error(
                400,
                f"max_tokens must be <= {OPENAI_MAX_TOKENS_LIMIT} for this deployment.",
                param="max_tokens",
            )
        return requested

    # ---------------------------------------------------------------- endpoints
    @app.get("/healthz")
    async def healthz(self) -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/generate", response_model=GenerateResponse)
    async def generate(self, req: GenerateRequest):
        request_id = f"gen-{uuid.uuid4().hex}"
        prompt = self._chat_prompt([{"role": "user", "content": req.prompt}])
        try:
            self._check_prompt_length(prompt, req.max_new_tokens)
        except PromptTooLongError as exc:
            return JSONResponse(status_code=400, content={"detail": str(exc)})

        params = SamplingParams(
            temperature=GENERATE_TEMPERATURE,
            top_p=GENERATE_TOP_P,
            repetition_penalty=GENERATE_REPETITION_PENALTY,
            max_tokens=req.max_new_tokens,
            stop_token_ids=self.stop_token_ids,
        )
        start = time.perf_counter()
        output = await self._complete(prompt, params, request_id)
        logger.info(
            "generate request_id=%s prompt_tokens=%d completion_tokens=%d latency_ms=%.1f",
            request_id,
            len(output.prompt_token_ids or []),
            len(output.outputs[0].token_ids),
            (time.perf_counter() - start) * 1000,
        )
        return GenerateResponse(text=output.outputs[0].text)

    @app.get("/v1/models")
    async def list_models(self) -> dict[str, Any]:
        return {
            "object": "list",
            "data": [
                {
                    "id": SERVED_MODEL_NAME,
                    "object": "model",
                    "created": self.created,
                    "owned_by": "qwen-k8s-serve",
                    "max_model_len": MAX_MODEL_LEN,
                }
            ],
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(self, req: ChatCompletionRequest):
        if (err := self._model_error(req.model)) is not None:
            return err
        max_tokens = self._resolve_max_tokens(req.max_completion_tokens or req.max_tokens)
        if isinstance(max_tokens, JSONResponse):
            return max_tokens

        messages = [
            {"role": "system" if m.role == "developer" else m.role, "content": message_text(m.content)}
            for m in req.messages
        ]
        prompt = self._chat_prompt(messages)
        try:
            self._check_prompt_length(prompt, max_tokens)
        except PromptTooLongError as exc:
            return openai_error(400, str(exc), param="messages", code="context_length_exceeded")

        params = self._openai_sampling_params(req, max_tokens)
        request_id = f"chatcmpl-{uuid.uuid4().hex}"
        created = int(time.time())

        if req.stream:
            include_usage = bool(req.stream_options and req.stream_options.include_usage)
            return StreamingResponse(
                self._chat_stream(prompt, params, request_id, created, include_usage),
                media_type="text/event-stream",
            )

        output = await self._complete(prompt, params, request_id)
        return {
            "id": request_id,
            "object": "chat.completion",
            "created": created,
            "model": SERVED_MODEL_NAME,
            "choices": [
                {
                    "index": c.index,
                    "message": {"role": "assistant", "content": c.text},
                    "logprobs": None,
                    "finish_reason": c.finish_reason,
                }
                for c in output.outputs
            ],
            "usage": usage([output]),
        }

    async def _chat_stream(
        self,
        prompt: str,
        params: SamplingParams,
        request_id: str,
        created: int,
        include_usage: bool,
    ) -> AsyncIterator[str]:
        base = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": SERVED_MODEL_NAME,
        }
        sent = [""] * params.n
        final: RequestOutput | None = None
        try:
            yield sse(
                {
                    **base,
                    "choices": [
                        {"index": i, "delta": {"role": "assistant", "content": ""}, "logprobs": None, "finish_reason": None}
                        for i in range(params.n)
                    ],
                }
            )
            async for output in self._stream(prompt, params, request_id):
                final = output
                for c in output.outputs:
                    delta = c.text[len(sent[c.index]):]
                    sent[c.index] = c.text
                    if delta or c.finish_reason:
                        yield sse(
                            {
                                **base,
                                "choices": [
                                    {
                                        "index": c.index,
                                        "delta": {"content": delta} if delta else {},
                                        "logprobs": None,
                                        "finish_reason": c.finish_reason,
                                    }
                                ],
                            }
                        )
            if include_usage and final is not None:
                yield sse({**base, "choices": [], "usage": usage([final])})
        except Exception:
            logger.exception("Streaming chat completion failed request_id=%s", request_id)
            yield sse({"error": {"message": "Internal server error", "type": "server_error", "param": None, "code": None}})
        yield "data: [DONE]\n\n"

    @app.post("/v1/completions")
    async def completions(self, req: CompletionRequest):
        if (err := self._model_error(req.model)) is not None:
            return err
        max_tokens = self._resolve_max_tokens(req.max_tokens)
        if isinstance(max_tokens, JSONResponse):
            return max_tokens

        prompts = [req.prompt] if isinstance(req.prompt, str) else req.prompt
        if not prompts or any(not p for p in prompts):
            return openai_error(400, "prompt must be a non-empty string or list of strings", param="prompt")
        if req.stream and len(prompts) > 1:
            return openai_error(400, "Streaming supports a single prompt only", param="prompt")
        try:
            for p in prompts:
                self._check_prompt_length(p, max_tokens)
        except PromptTooLongError as exc:
            return openai_error(400, str(exc), param="prompt", code="context_length_exceeded")

        params = self._openai_sampling_params(req, max_tokens)
        request_id = f"cmpl-{uuid.uuid4().hex}"
        created = int(time.time())

        if req.stream:
            include_usage = bool(req.stream_options and req.stream_options.include_usage)
            return StreamingResponse(
                self._completion_stream(prompts[0], params, request_id, created, include_usage),
                media_type="text/event-stream",
            )

        outputs = await asyncio.gather(
            *(self._complete(p, params, f"{request_id}-{i}") for i, p in enumerate(prompts))
        )
        return {
            "id": request_id,
            "object": "text_completion",
            "created": created,
            "model": SERVED_MODEL_NAME,
            "choices": [
                {
                    "index": p_idx * params.n + c.index,
                    "text": c.text,
                    "logprobs": None,
                    "finish_reason": c.finish_reason,
                }
                for p_idx, output in enumerate(outputs)
                for c in output.outputs
            ],
            "usage": usage(list(outputs)),
        }

    async def _completion_stream(
        self,
        prompt: str,
        params: SamplingParams,
        request_id: str,
        created: int,
        include_usage: bool,
    ) -> AsyncIterator[str]:
        base = {
            "id": request_id,
            "object": "text_completion",
            "created": created,
            "model": SERVED_MODEL_NAME,
        }
        sent = [""] * params.n
        final: RequestOutput | None = None
        try:
            async for output in self._stream(prompt, params, request_id):
                final = output
                for c in output.outputs:
                    delta = c.text[len(sent[c.index]):]
                    sent[c.index] = c.text
                    if delta or c.finish_reason:
                        yield sse(
                            {
                                **base,
                                "choices": [
                                    {
                                        "index": c.index,
                                        "text": delta,
                                        "logprobs": None,
                                        "finish_reason": c.finish_reason,
                                    }
                                ],
                            }
                        )
            if include_usage and final is not None:
                yield sse({**base, "choices": [], "usage": usage([final])})
        except Exception:
            logger.exception("Streaming completion failed request_id=%s", request_id)
            yield sse({"error": {"message": "Internal server error", "type": "server_error", "param": None, "code": None}})
        yield "data: [DONE]\n\n"


deployment = QwenVLLMDeployment.bind()
