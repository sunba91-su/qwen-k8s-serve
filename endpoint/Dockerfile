FROM mirror.asiyabani.id.ir/rayproject/ray:2.40.0-py310-cpu
ENV PYTHONUNBUFFERED=1 \
    RAY_SERVE_ENABLE_EXPERIMENTAL_STREAMING=1 \
    MODEL_ID="Qwen/Qwen2.5-0.5B-Instruct" \
    MODEL_CACHE_DIR="/models" \
    VLLM_CPU_KVCACHE_SPACE=1 \
    VLLM_CPU_OMP_THREADS_BIND=nobind \
    OMP_NUM_THREADS=4 


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
RUN pip install "numpy<2.0.0" "pyarrow>=14.0.1" --upgrade
COPY --chown=ray:users serve_script.py serve_config.yaml ./

EXPOSE 8000

ENV TORCHDYNAMO_DISABLE=1

CMD ["serve", "run", "serve_config.yaml"]