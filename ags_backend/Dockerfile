FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt requirements-local.txt requirements-models.txt requirements-oracle.txt ./
ARG INSTALL_LOCAL_EMBEDDINGS=true
ARG INSTALL_CLOUD_MODELS=true
ARG INSTALL_ORACLE=false
# Retained for existing build callers; OCI was already in the shared lock.
ARG INSTALL_OCI=false
RUN pip install --no-cache-dir -r requirements.txt && if [ "$INSTALL_LOCAL_EMBEDDINGS" = "true" ]; then pip install --no-cache-dir -r requirements-local.txt -c requirements.txt; fi && if [ "$INSTALL_CLOUD_MODELS" = "true" ]; then pip install --no-cache-dir -r requirements-models.txt -c requirements.txt; fi
RUN if [ "$INSTALL_ORACLE" = "true" ]; then pip install --no-cache-dir -r requirements-oracle.txt -c requirements.txt; fi
COPY ags_app ./ags_app
RUN useradd --create-home --uid 10001 aegis && mkdir -p /data && chown aegis:aegis /data /app
USER aegis
ENV AEGIS_STORAGE_ROOT=/data PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "ags_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
