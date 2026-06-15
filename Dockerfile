FROM python:3.11-slim

# Install the FFmpeg binary required for the subprocess
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Flask application
COPY . .

EXPOSE 8080

# Use Gunicorn to handle concurrent streams efficiently
CMD ["gunicorn", "-w", "2", "--threads", "4", "--worker-class", "gthread", "-b", "0.0.0.0:8080", "app:app"]
