FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt requirements.lock requirements-local.txt requirements-local.lock requirements-oci.txt ./
ARG INSTALL_LOCAL_EMBEDDINGS=true
RUN pip install --no-cache-dir -r requirements.lock && if [ "$INSTALL_LOCAL_EMBEDDINGS" = "true" ]; then pip install --no-cache-dir -r requirements-local.lock -c requirements.lock --extra-index-url https://download.pytorch.org/whl/cpu; fi
COPY app ./app
RUN useradd --create-home --uid 10001 aegis && mkdir -p /data && chown aegis:aegis /data /app
USER aegis
ENV AEGIS_STORAGE_ROOT=/data PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
