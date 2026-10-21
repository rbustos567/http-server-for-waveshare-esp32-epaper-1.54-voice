FROM python:3.11-slim

# Evita la generación de archivos .pyc y fuerza salida no amortiguada para logs en tiempo real
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Instalar librerías nativas del sistema para procesamiento de audio y utilidades
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

# Descargar y descomprimir Piper TTS para arquitectura ARM64 (aarch64)
RUN wget -q https://github.com/rhasspy/piper/releases/latest/download/piper_linux_aarch64.tar.gz -O piper.tar.gz && \
    tar -xzf piper.tar.gz -C /usr/local/ && \
    rm piper.tar.gz && \
    ln -s /usr/local/piper/piper /usr/local/bin/piper

# Descargar y descomprimir el modelo de Vosk dentro de la imagen
RUN mkdir -p models && \
    wget -q https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip -O vosk-es.zip && \
    unzip vosk-es.zip -d models/ && mv models/vosk-model-small-es-0.42 models/vosk-es && rm vosk-es.zip && \
    wget -q https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -O vosk-en.zip && \
    unzip vosk-en.zip -d models/ && mv models/vosk-model-small-en-us-0.15 models/vosk-en && rm vosk-en.zip

# Descargar el modelo de voz de Piper (TTS: archivo .onnx y su .json)
RUN mkdir -p voices && \
    wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/high/en_US-lessac-high.onnx -O voices/en_US-lessac-high.onnx && \
    wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/high/en_US-lessac-high.onnx.json -O voices/en_US-lessac-high.onnx.json && \
    wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/claude/high/es_MX-claude-high.onnx -O voices/es_MX-claude-high.onnx && \
    wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/claude/high/es_MX-claude-high.onnx.json -O voices/es_MX-claude-high.onnx.json
# Copiar requerimientos e instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el código fuente
COPY . /app

# Exponer el puerto de la API REST del motor de IA
EXPOSE 8000

# Ejecutamos directamente el módulo config_loader para probar la carga
CMD ["python3", "voice_commander.py"]
