# Skill-index service (brief 36): BM25 + embeddings over the knowledge bank, the in-process index's own code.
# Build from the repo root:  docker build -f agent/skill_service/Dockerfile -t fda-skill-index:1 .
# Run:  docker run --rm -p 8088:8088 -v <bank checkout>:/bank:ro fda-skill-index:1
# The bank is never copied into the image (it is private); it is mounted read-only. The embedding model
# (BAAI/bge-small-en-v1.5, MIT) is fetched at build time, so the running container needs no network.
# Packages: fastembed 0.9.1 (Apache-2.0), onnxruntime (MIT), numpy (BSD), PyYAML (MIT); licences checked 2026-11-10.
FROM python:3.12-slim
RUN pip install --no-cache-dir fastembed==0.9.1 numpy==2.5.4 PyYAML==6.0.3
ENV FASTEMBED_CACHE_PATH=/opt/models HF_HUB_OFFLINE=0
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/opt/models')"
ENV HF_HUB_OFFLINE=1 FDA_KNOWLEDGE=/bank FDA_CORE=/app/core PORT=8088
COPY agent/core/bank.py agent/core/skill_index.py /app/core/
COPY agent/skill_service/server.py /app/skill_service/server.py
RUN useradd -u 10001 -M app
USER 10001
EXPOSE 8088
CMD ["python", "/app/skill_service/server.py"]
