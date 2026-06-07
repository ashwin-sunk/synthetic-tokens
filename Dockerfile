FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirementspiiapi.txt .
RUN pip install --no-cache-dir -r requirementspiiapi.txt

# Bake spaCy model into image (no runtime download)
RUN python -m spacy download en_core_web_lg

# Bake GLiNER weights into image at build time
# Pass token if model requires authentication: docker build --build-arg HF_TOKEN=hf_... .
ARG HF_TOKEN
ENV HUGGINGFACE_TOKEN=${HF_TOKEN}
RUN python -c "from gliner import GLiNER; GLiNER.from_pretrained('urchade/gliner_medium-v2.1')" || \
    echo "[WARN] GLiNER pre-cache skipped — will download at runtime if HUGGINGFACE_TOKEN is set"

COPY api.py synthetic_pii_generator.py ./

EXPOSE 8000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
