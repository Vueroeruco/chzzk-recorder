# 1. Base Image: Official Playwright image for stability
FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy

# 2. Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 3. Install ffmpeg (Playwright image is Ubuntu-based)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 4. Set up working directory
WORKDIR /app

# 5. Install Python dependencies
# First, copy only the requirements file to leverage Docker cache
COPY ./chzzk_recorder/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy the rest of the application code
COPY ./chzzk_recorder /app

# 7. Command to run the application
# The base image uses 'python3'
CMD ["python3", "watcher.py"]