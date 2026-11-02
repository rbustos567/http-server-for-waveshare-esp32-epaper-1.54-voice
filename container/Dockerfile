FROM python:3.11-slim

# Prevent Python from writing pyc files and keep stdout/stderr unbuffered for real-time logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install native system libraries for audio processing and utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    portaudio19-dev \
    libasound2-dev \
    pulseaudio-utils \
    alsa-utils \
    libatomic1 \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Download and extract Piper TTS for ARM64 (aarch64) architecture
RUN wget -q https://github.com/rhasspy/piper/releases/latest/download/piper_linux_aarch64.tar.gz -O piper.tar.gz && \
    tar -xzf piper.tar.gz -C /usr/local/ && \
    rm piper.tar.gz && \
    ln -s /usr/local/piper/piper /usr/local/bin/piper

# Download and extract the Vosk model inside the image
RUN mkdir -p models && \
    wget -q https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip -O vosk-es.zip && \
    unzip vosk-es.zip -d models/ && mv models/vosk-model-small-es-0.42 models/vosk-es && rm vosk-es.zip && \
    wget -q https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -O vosk-en.zip && \
    unzip vosk-en.zip -d models/ && mv models/vosk-model-small-en-us-0.15 models/vosk-en && rm vosk-en.zip

# Download the Piper voice model (TTS: .onnx file and its .json)
RUN mkdir -p voices && \
    wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/high/en_US-lessac-high.onnx -O voices/en_US-lessac-high.onnx && \
    wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/high/en_US-lessac-high.onnx.json -O voices/en_US-lessac-high.onnx.json && \
    wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/claude/high/es_MX-claude-high.onnx -O voices/es_MX-claude-high.onnx && \
    wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/claude/high/es_MX-claude-high.onnx.json -O voices/es_MX-claude-high.onnx.json

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . /app

# Expose the port for the AI engine REST API
EXPOSE 8000

# Execute the main command to run the application
CMD ["python3", "voice_commander.py"]
