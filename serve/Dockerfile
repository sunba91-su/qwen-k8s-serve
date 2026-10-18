FROM registry.apk-group.net/mirror/rayproject/ray:2.40.0-py310-cpu
ENV PYTHONUNBUFFERED=1 \
    RAY_SERVE_ENABLE_EXPERIMENTAL_STREAMING=1 \
    MODEL_ID="Qwen/Qwen2.5-0.5B-Instruct" \
    MODEL_CACHE_DIR="/models" \
    VLLM_CPU_KVCACHE_SPACE=1 \
    VLLM_CPU_OMP_THREADS_BIND=nobind \
    OMP_NUM_THREADS=4 \
    HTTPS_PROXY=socks5://172.25.4.4:2283 \
    HTTP_PROXY=socks5://172.25.4.4:2283 \
    ALL_PROXY=socks5://172.25.4.4:2283 


USER root
RUN apt-get update && apt-get install -y --no-install-recommends libnuma1 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /models && chown -R ray:users /models && chmod 777 /models
USER ray

WORKDIR /home/ray/app

COPY --chown=ray:users requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y cupy-cuda12x \
    && pip install --no-cache-dir --force-reinstall \
        "numpy==2.2.6" "pandas==2.2.3" "pyarrow==17.0.0" \
        "scipy==1.15.3" "fastapi==0.139.1"

COPY --chown=ray:users serve_script.py serve_config.yaml ./

EXPOSE 8000

ENV TORCHDYNAMO_DISABLE=1

CMD ["serve", "run", "serve_config.yaml"]