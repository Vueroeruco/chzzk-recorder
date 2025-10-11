# 1. Base Image Setup
FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy as base

# 2. Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 3. Set up working directory
WORKDIR /app

# 4. System dependencies (ffmpeg for muxing, wget/ca-cert for downloader)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 4.1 Install N_m3u8DL-RE (for parallel HLS) with pinned version + SHA256 verify
ARG NMD_VER=v0.3.0-beta
ARG NMD_NAME=N_m3u8DL-RE_v0.3.0-beta_linux-x64_20241203.tar.gz
ARG NMD_SHA256=35205154911E8505A7031999B0E35120CDA4E2433D964F3A66D6EE9F322398BA
RUN set -eux; \
    cd /tmp; \
    wget -O nmd.tar.gz "https://github.com/nilaoda/N_m3u8DL-RE/releases/download/${NMD_VER}/${NMD_NAME}"; \
    echo "${NMD_SHA256}  nmd.tar.gz" | sha256sum -c -; \
    mkdir -p /tmp/nmd; tar -xzf nmd.tar.gz -C /tmp/nmd; \
    # binary may be at top-level or nested; copy if exists
    if [ -f /tmp/nmd/N_m3u8DL-RE ]; then cp /tmp/nmd/N_m3u8DL-RE /usr/local/bin/; fi; \
    if [ -f /tmp/nmd/*/N_m3u8DL-RE ]; then cp /tmp/nmd/*/N_m3u8DL-RE /usr/local/bin/; fi; \
    chmod +x /usr/local/bin/N_m3u8DL-RE; \
    rm -rf /tmp/nmd nmd.tar.gz; \
    /usr/local/bin/N_m3u8DL-RE -h >/dev/null

# 5. Install Python dependencies
# First, copy only the requirements file to leverage Docker cache
COPY ./chzzk_recorder/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy the rest of the application code
COPY ./chzzk_recorder /app

# 7. Command to run the application
# The base image uses 'python3'
CMD ["python3", "watcher.py"]
