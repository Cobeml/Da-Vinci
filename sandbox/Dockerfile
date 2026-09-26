FROM node:22-slim AS node
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libxrender1 libxext6 && rm -rf /var/lib/apt/lists/*
COPY requirements.lock /opt/requirements.txt
RUN pip install --no-cache-dir -r /opt/requirements.txt
COPY build.py evaluate.py integrate.py families.py invoke.py adapt.py /opt/
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY ui /opt/ui
ENV OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
USER 65534:65534
WORKDIR /output
