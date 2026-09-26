FROM node:22-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c AS node
WORKDIR /opt/ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci --omit=dev
COPY ui/check.cjs ./
FROM python:3.11-slim@sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libxrender1 libxext6 && rm -rf /var/lib/apt/lists/*
COPY requirements.lock /opt/requirements.txt
RUN pip install --no-cache-dir -r /opt/requirements.txt
COPY build.py evaluate.py integrate.py families.py invoke.py adapt.py /opt/
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /opt/ui /opt/ui
ENV OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
USER 65534:65534
WORKDIR /output
