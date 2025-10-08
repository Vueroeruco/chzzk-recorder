# 1. Base Image Setup
FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy as base

# 2. FFmpeg Stage: Use a static build of FFmpeg 7
FROM mwader/static-ffmpeg:7.0 as ffmpeg

# 3. Final Image: Combine base and FFmpeg
FROM base

# Copy FFmpeg binaries from the ffmpeg stage
COPY --from=ffmpeg /ffmpeg /usr/local/bin/
COPY --from=ffmpeg /ffprobe /usr/local/bin/

# 4. Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 5. Set up working directory
WORKDIR /app

# 6. Install Python dependencies
# First, copy only the requirements file to leverage Docker cache
COPY ./chzzk_recorder/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 7. Copy the rest of the application code
COPY ./chzzk_recorder /app

# 8. Command to run the application
# The base image uses 'python3'
CMD ["python3", "watcher.py"]
