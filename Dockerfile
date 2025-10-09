# 1. Base Image Setup
FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy as base

# 2. Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 3. Set up working directory
WORKDIR /app

# 4. Install Python dependencies
# First, copy only the requirements file to leverage Docker cache
COPY ./chzzk_recorder/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of the application code
COPY ./chzzk_recorder /app

# 6. Command to run the application
# The base image uses 'python3'
CMD ["python3", "watcher.py"]
