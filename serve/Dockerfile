FROM rayproject/ray:2.10.0-py310-cpu
ENV PYTHONUNBUFFERED=1 \
    RAY_SERVE_ENABLE_EXPERIMENTAL_STREAMING=1 \
    MODEL_ID="Qwen/Qwen2.5-0.5B-Instruct" \
    MODEL_CACHE_DIR="/models" \
    HTTPS_PROXY=socks5://172.25.4.4:2283 \
    HTTP_PROXY=socks5://172.25.4.4:2283 \
    ALL_PROXY=socks5://172.25.4.4:2283 

USER root
RUN mkdir -p /models && chown ray:users /models
USER ray

WORKDIR /home/ray/app

COPY --chown=ray:users requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=ray:users serve_script.py .

EXPOSE 8000

CMD ["serve", "run", "serve_script:deployment", "--host", "0.0.0.0", "--port", "8000"]