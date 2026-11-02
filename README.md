# HTTP Server For Waveshare ESP32-S3-ePaper-1.54 (Voice Commander Server)

The system operates through a split architecture: on one side, a Docker container serves as the core AI engine via a FastAPI REST API, dynamically integrating speech recognition (Vosk STT) and speech synthesis (Piper TTS). On the other side, an executable script on the host operating system (host_runner) acts as a secure intermediary to execute terminal commands, manage persistent states, and control local or networked physical hardware. This design allows users to issue voice commands from the **Microcontroller:** Developed for the [ESP32-ePaper-Client Repository]([https://github.com/tu_usuario/tu-repositorio-microcontrolador](https://github.com/rbustos567/waveshare-esp32-epaper-1.54-voice-client.git)) running firmware under ESP-IDF., which are transcribed, validated, and translated into real actions on the system, returning visual or synthesized feedback.

This repository contains the backend components for the Voice Commander project, split into two main parts:
1. **Docker Container (`container/`)**: Runs the FastAPI AI engine, Vosk STT, and Piper TTS.
2. **Host Broker (`host_broker/`)**: Runs `host_runner.py` directly on the host operating system to execute local system commands and hardware integrations.

---

## Prerequisites

- **Docker & Docker Compose** installed on your system.
- **Python 3.10+** installed on the host machine.
- Ports **8000** (Docker API) and **8001** (Host Runner) available.

---
# Installation

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
# (Optional) Check logs in real time:
docker compose logs -f voice_commander_app
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
# Adding New Commands

To add a new custom voice command to the system, you need to update both the backend container configurations and the host broker definitions. Follow these steps:

## Step 1: Define the Command in the Host Broker
Add your command execution logic in host_broker/commands_config.json. The key you choose here will act as the unique identifier for the command.

```bash
{
  "your_command_key": {
    "description": "Description of what the command does",
    "command": "your_actual_terminal_command_here"
  }
}
```
## Step 2: Configure the Intent in the Container
Open container/config.json and add a matching entry under the "commands" object. The key must exactly match the one defined in commands_config.json.   

```bash
"commands": {
  "your_command_key": {
    "phrases": ["phrase one to trigger", "alternative phrase"],
    "command": "your_actual_terminal_command_here",
    "formatter": "your_formatter_function_name",
    "confirmation_prompt": "Do you want to run this command?",
    "success_message": "Command executed successfully.",
    "requires_confirmation": true,
    "tts_output": false
  }
}
```
## Step 3: Implement a Custom Formatter (Optional)
If your command requires custom text parsing or formatting for the output display, you must implement the formatter function inside container/formatters.py.   
Open container/formatters.py and define your function matching the name specified in container/config.json:

```bash
def your_formatter_function_name(raw_output: str) -> str:
    # Process or parse the raw command output string here
    formatted_output = raw_output.strip()
    return formatted_output
```
Once these three steps are completed, rebuild and restart your container to apply the changes:

```bash
docker compose build
docker compose up -d
```
# Switching to Spanish and Adding Spanish Commands
The system includes built-in Spanish support via a dedicated configuration template. Follow these steps to activate it and add your custom Spanish commands:

## Step 1: Enable the Spanish Configuration File
Rename the Spanish backup configuration file (container/config.json.es) so that the container uses it as its primary configuration (container/config.json):

```bash
mv container/config.json.es container/config.json
```

## Step 2: Define the Command in the Host Broker
Ensure that the command you want to execute is registered in the corresponding host configuration file (host_broker/commands_config.json):

```bash
{
  "tu_comando_en_espanol": {
    "description": "Description of what the command does",
    "command": "your_terminal_command_here"
  }
}
```

## Step 3: Configure the Intent in the Container
Open container/config.json and add or modify the entry under the "commands" object. The key must exactly match the one defined in the host broker:

```bash
"commands": {
  "tu_comando_en_espanol": {
    "phrases": ["spanish phrase one", "alternative phrase to trigger"],
    "command": "your_terminal_command_here",
    "formatter": "your_formatter_function_name",
    "confirmation_prompt": "Do you want to run this command?",
    "success_message": "Command executed successfully.",
    "requires_confirmation": true,
    "tts_output": false
  }
}
```

## Step 4: Implement a Custom Formatter (Optional)
If you need to process the command output before displaying or synthesizing it, implement the function inside container/formatters.py using the exact name specified in the JSON:

```bash
def your_formatter_function_name(raw_output: str) -> str:
    # Process or format the text output here
    formatted_output = raw_output.strip()
    return formatted_output
```

## Step 5: Rebuild and Restart the Container
To apply the changes and ensure the container loads the new configuration, rebuild and launch the Docker service:

```bash
docker compose build
docker compose up -d
```
