import os
import json
import subprocess
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
import uvicorn

CONFIG_FILE = "commands_config.json"
API_TOKEN = os.getenv("HOST_API_TOKEN", "my_secure_voice_token_123")
PORT = int(os.getenv("HOST_RUNNER_PORT", 8001))

if not os.path.exists(CONFIG_FILE):
    raise FileNotFoundError(f"Configuration file '{CONFIG_FILE}' not found on host.")

with open(CONFIG_FILE, "r") as f:
    COMMANDS_CONFIG = json.load(f)

app = FastAPI(title="Voice Commander Host Broker")

class ExecRequest(BaseModel):
    command_key: str
    params: dict = {}

@app.post("/exec")
def execute_command(req: ExecRequest, authorization: str = Header(None)):
    if authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized token")

    key = req.command_key
    if key not in COMMANDS_CONFIG:
        raise HTTPException(status_code=400, detail=f"Command key '{key}' not whitelisted")

    cmd_template = COMMANDS_CONFIG[key].get("command")
    try:
        cmd = cmd_template.format(**req.params) if req.params else cmd_template
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing parameter for command: {e}")

    print(f"⚡ Executing host command: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20)
        output = result.stdout.strip() if result.returncode == 0 else result.stderr.strip()

        print(f"📄 Salida obtenida:\n{output}")

        return {
            "status": "success" if result.returncode == 0 else "error",
            "returncode": result.returncode,
            "output": output
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
