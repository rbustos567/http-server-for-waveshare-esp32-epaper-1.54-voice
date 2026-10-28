import os
import json
import logging
import subprocess
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("HostBroker")

CONFIG_FILE = "commands_config.json"
API_TOKEN = os.getenv("HOST_API_TOKEN", "my_secure_voice_token_123")
PORT = int(os.getenv("HOST_RUNNER_PORT", 8001))

if not os.path.exists(CONFIG_FILE):
    logger.critical(f"Configuration file '{CONFIG_FILE}' not found on host.")
    raise FileNotFoundError(f"Configuration file '{CONFIG_FILE}' not found on host.")

logger.info(f"Loading commands configuration from {CONFIG_FILE}...")
with open(CONFIG_FILE, "r") as f:
    COMMANDS_CONFIG = json.load(f)

app = FastAPI(title="Voice Commander Host Broker")

class ExecRequest(BaseModel):
    """
    Data model representing an incoming command execution request payload.
    Supports optional dictionary parameters (e.g., {'argument': 'user voice prompt'}).
    """
    command_key: str
    params: dict = {}

@app.post("/exec")
def execute_command(req: ExecRequest, authorization: str = Header(None)):
    """
    Validates bearer token authentication, checks command authorization against 
    the whitelist, dynamically interpolates <argument> parameters into shell templates,
    and executes the system command via subprocess, returning raw output or error states.
    """
    if authorization != f"Bearer {API_TOKEN}":
        logger.warning("Unauthorized execution attempt with invalid or missing token.")
        raise HTTPException(status_code=401, detail="Unauthorized token")

    key = req.command_key
    if key not in COMMANDS_CONFIG:
        logger.warning(f"Command key '{key}' requested but not whitelisted in configuration.")
        raise HTTPException(status_code=400, detail=f"Command key '{key}' not whitelisted")

    cmd_template = COMMANDS_CONFIG[key].get("command", "")
    
    # Dynamically replace <argument> placeholder if provided in params
    if req.params and "argument" in req.params:
        cmd_template = cmd_template.replace("<argument>", req.params["argument"])

    try:
        cmd = cmd_template.format(**req.params) if req.params else cmd_template
    except KeyError as e:
        logger.error(f"Missing parameter for command '{key}': {e}")
        raise HTTPException(status_code=400, detail=f"Missing parameter for command: {e}")

    logger.info(f"⚡ Executing host command: {cmd}")
    try:
        # Increased timeout to 60s to support heavy local model runs (e.g., Ollama / LLMs)
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        output = result.stdout.strip() if result.returncode == 0 else result.stderr.strip()

        logger.info(f"📄 Raw output obtained:\n{output}")

        return {
            "status": "success" if result.returncode == 0 else "error",
            "returncode": result.returncode,
            "output": output
        }
    except subprocess.TimeoutExpired:
        logger.error(f"Command execution timed out after 60 seconds: {cmd}")
        raise HTTPException(status_code=504, detail="Command execution timed out.")
    except Exception as e:
        logger.error(f"Exception occurred while executing command '{key}': {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    logger.info(f"Starting Voice Commander Host Broker on port {PORT}...")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
