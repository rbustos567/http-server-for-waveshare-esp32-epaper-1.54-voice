# HTTP Server For Waveshare ESP32-S3-ePaper-1.54 (Voice Commander Server)

This repository contains the backend components for the Voice Commander project, split into two main parts:
1. **Docker Container (`container/`)**: Runs the FastAPI AI engine, Vosk STT, and Piper TTS.
2. **Host Broker (`host_broker/`)**: Runs `host_runner.py` directly on the host operating system to execute local system commands and hardware integrations.

---

## Prerequisites

- **Docker & Docker Compose** installed on your system.
- **Python 3.10+** installed on the host machine.
- Ports **8000** (Docker API) and **8001** (Host Runner) available.

---

## Step 1: Clone the Repository

Clone the project to your local machine or single-board computer (such as an Orange Pi 6 plus):

```bash
git clone [git@github.com:rbustos567/http-server-for-waveshare-esp32-epaper-1.54-voice.git](https://github.com/rbustos567/http-server-for-waveshare-esp32-epaper-1.54-voice.git)
cd http-server-for-waveshare-esp32-epaper-1.54-voice
```

## Step 2: Start the Voice Commander Docker Container

1. Ensure you are in the root directory where docker-compose.yml is located.
2. Build and launch the container in detached mode (it will automatically restart on system reboots thanks to restart: unless-stopped):
```bash
docker compose up --build -d
```
3. Verify that the container is running properly:
```bash
docker ps
```

## Step 3: Run the Host Runner (host_runner.py)
Because the host runner interacts directly with host hardware and system automation scripts, it must run on the host OS.

#### Option A: Manual Execution
1. Navigate to the host_broker directory:

```bash
cd host_broker
```

2. Run the script with Python 3:

```bash
python3 host_runner.py
```
#### Option B: Automatic Execution via Systemd (Recommended for Production / SBCs)

To make host_runner.py start automatically on boot alongside Docker:

1. Create a systemd service file:

```bash
sudo nano /etc/systemd/system/host_runner.service
```

2. Paste the following configuration (replace YOUR_USERNAME and the absolute path with your actual system details):

```bash
[Unit]
Description=Voice Commander Host Runner Service
After=network.target docker.service

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/http-server-for-waveshare-esp32-epaper-1.54-voice/host_broker
ExecStart=/usr/bin/python3 host_runner.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

3. Save and close the editor, then enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable host_runner.service
sudo systemctl start host_runner.service
```
