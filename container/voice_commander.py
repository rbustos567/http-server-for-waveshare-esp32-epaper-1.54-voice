import os
import io
import json
import wave
import time
import base64
import logging
import subprocess
import requests
import formatters
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Security, Request, Response, Depends
from fastapi.security.api_key import APIKeyHeader, APIKey
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from vosk import Model, KaldiRecognizer
from sentence_transformers import SentenceTransformer, util

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("VoiceCommander")

app = FastAPI(title="Voice Commander AI Engine")

# Ensure exposure of custom headers for the ESP32 client
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Server-Status",
        "X-Transcription",
        "X-Requires-Followup",
        "X-Cmd-Output"
    ],
)

# These API keys must match those configured on the ESP32 client
API_KEY_SECRET = "password123x"
API_KEY_NAME = "API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)):
    """
    Validates the incoming API key against the secret server configuration.
    Raises an HTTP 401 Unauthorized exception if the key is invalid or missing.
    """
    if api_key == API_KEY_SECRET:
        return api_key
    logger.warning("Unauthorized access attempt with invalid or missing API Key.")
    raise HTTPException(status_code=401, detail="Unauthorized: Invalid or missing API Key")

MODEL_PATH = os.getenv("VOSK_MODEL_PATH", "/app/models/vosk-en")
CONFIG_PATH = "config.json"
HOST_RUNNER_URL = os.getenv("HOST_RUNNER_URL", "http://host.docker.internal:8001")
HOST_API_TOKEN = os.getenv("HOST_API_TOKEN", "my_secure_voice_token_123")

if not os.path.exists(MODEL_PATH):
    logger.critical(f"Vosk model not found at path: {MODEL_PATH}")
    raise FileNotFoundError(f"Vosk model not found at {MODEL_PATH}")

logger.info(f"Loading Vosk model from {MODEL_PATH}...")
vosk_model = Model(MODEL_PATH)

with open(CONFIG_PATH, "r") as f:
    INTENTS_CONFIG = json.load(f).get("commands", {})

logger.info("Initializing SentenceTransformer model for intent matching...")
nlp_model = SentenceTransformer("all-MiniLM-L6-v2")
INTENT_MAP = []
INTENT_PHRASES = []

for key, val in INTENTS_CONFIG.items():
    for phrase in val.get("phrases", []):
        INTENT_PHRASES.append(phrase)
        INTENT_MAP.append(key)

PHRASE_EMBEDDINGS = nlp_model.encode(INTENT_PHRASES, convert_to_tensor=True)

# User Session Memory Storage
SESSIONS = {}

def sanitize_header(text: str) -> str:
    """
    Cleans target text for safe transmission via HTTP headers by replacing 
    newlines, carriage returns, and tabs with clean whitespace.
    """
    if not text:
        return ""
    return str(text).replace("\n", " ").replace("\r", " ").replace("\t", " ")

def get_session(session_id: str):
    """
    Retrieves or initializes an active user session state based on session_id.
    Automatically expires and resets sessions inactive for more than 60 seconds.
    """
    now = time.time()
    if session_id not in SESSIONS or (now - SESSIONS[session_id]["timestamp"]) > 60:
        logger.info(f"Creating or resetting session state for ID: {session_id}")
        SESSIONS[session_id] = {
            "context": None,
            "pending_action": None,
            "timestamp": now
        }
    SESSIONS[session_id]["timestamp"] = now
    return SESSIONS[session_id]

def generate_piper_tts_bytes(text: str) -> bytes:
    """
    Generates raw binary WAV audio bytes using Piper TTS engine from text input,
    handling temporary file generation and cleanup securely.
    """
    try:
        output_file = "/tmp/response.wav"
        model_path = "/app/voices/en_US-lessac-high.onnx" # Switch to Spanish model if preferred
        
        cmd = f"echo '{text}' | piper --model {model_path} --output_file {output_file}"
        subprocess.run(cmd, shell=True, check=True)

        with open(output_file, "rb") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error generating Piper TTS audio: {e}")
        return b""

def transcribe_wav(audio_bytes: bytes) -> str:
    """
    Transcribes raw audio bytes into text using the Vosk offline speech recognition engine.
    """
    recognizer = KaldiRecognizer(vosk_model, 16000)
    recognizer.SetWords(True)
    chunk_size = 4000
    text = ""
    
    for i in range(0, len(audio_bytes), chunk_size):
        chunk = audio_bytes[i:i + chunk_size]
        if recognizer.AcceptWaveform(chunk):
            res = json.loads(recognizer.Result())
            text += " " + res.get("text", "")

    res = json.loads(recognizer.FinalResult())
    text += " " + res.get("text", "")
    return text.strip()

def call_host_broker(command_key: str, params: dict = {}):
    """
    Dispatches a verified execution command payload to the host runner broker via HTTP POST.
    """
    headers = {"Authorization": f"Bearer {HOST_API_TOKEN}"}
    payload = {"command_key": command_key, "params": params}
    try:
        logger.info(f"Dispatching command to host broker: {command_key}")
        res = requests.post(f"{HOST_RUNNER_URL}/exec", json=payload, headers=headers, timeout=40)
        return res.json()
    except Exception as e:
        logger.error(f"Failed to communicate with host runner broker: {e}")
        return {"status": "error", "output": str(e)}

@app.post("/process-audio", dependencies=[Depends(verify_api_key)])
async def process_audio(request: Request):
    """
    Main webhook endpoint processing incoming audio bytes from the ESP32 client,
    handling voice intent parsing, confirmation workflows, and execution responses.
    """
    audio_bytes = await request.body()
    comm_status = request.headers.get("X-Communication-Status", "active")

    if comm_status == "final" or len(audio_bytes) == 0:
        logger.info("Session closed or empty audio buffer received.")
        empty_headers = {
            "X-Server-Status": "closed",
            "X-Transcription": "",
            "X-Requires-Followup": "false",
            "X-Cmd-Output": "Session closed."
        }
        return Response(content=b"", media_type="audio/wav", headers=empty_headers)

    transcription = transcribe_wav(audio_bytes)
    logger.info(f"🎙️ Transcription received: '{transcription}'")

    if not transcription:
        msg = "No audio or speech detected."
        logger.warning(msg)
        audio_wav = generate_piper_tts_bytes(msg)
        headers = {
            "X-Server-Status": "ignored",
            "X-Transcription": "",
            "X-Requires-Followup": "false",
            "X-Cmd-Output": msg
        }
        return Response(content=audio_wav, media_type="audio/wav", headers=headers)

    session_id = "default_session"
    session = get_session(session_id)
    text_lower = transcription.lower()

    # --- STEP 5: EVALUATE CONFIRMATION RESPONSE (YES / NO) ---
    if session["context"] == "awaiting_confirmation":
        pending_cmd = session["pending_action"]
        session["context"] = None
        session["pending_action"] = None

        if any(w in text_lower for w in ["yes", "sure", "confirm", "ok", "yeah", "do it"]):
            logger.info(f"✅ Confirmation accepted. Executing command: {pending_cmd}")
            exec_res = call_host_broker(pending_cmd)

            intent_data = INTENTS_CONFIG.get(pending_cmd, {})
            success_msg = intent_data.get("success_message", "Command executed successfully.")
            host_output = exec_res.get("output", "")

            logger.debug(f"Host output received: '{host_output}'")

            if host_output is not None and host_output.strip() != "":
                cmd_out = host_output
            else:
                cmd_out = success_msg

            # --- APPLY FORMATTER IF CONFIGURED ---
            formatter_name = intent_data.get("formatter")
            if formatter_name and hasattr(formatters, formatter_name):
                formatter_func = getattr(formatters, formatter_name)
                formatted_output = formatter_func(cmd_out)
                cmd_out_header = str(formatted_output).replace("\n", " ").replace("\r", "")
            else:
                cmd_out_header = sanitize_header(cmd_out)

            audio_wav = generate_piper_tts_bytes(success_msg)
            headers = {
                "X-Server-Status": "success",
                "X-Transcription": sanitize_header(success_msg),
                "X-Requires-Followup": "false",
                "X-Cmd-Output": cmd_out_header
            }
            return Response(content=audio_wav, media_type="audio/wav", headers=headers)
        else:
            logger.info("❌ Action cancelled by user.")
            cancel_msg = "Action cancelled."
            audio_wav = generate_piper_tts_bytes(cancel_msg)
            headers = {
                "X-Server-Status": "cancelled",
                "X-Transcription": sanitize_header(cancel_msg),
                "X-Requires-Followup": "false",
                "X-Cmd-Output": sanitize_header(cancel_msg)
            }
            return Response(content=audio_wav, media_type="audio/wav", headers=headers)

    # --- STEP 3 & 4: FIND INTENT AND REQUEST CONFIRMATION ---
    user_emb = nlp_model.encode(transcription, convert_to_tensor=True)
    scores = util.cos_sim(user_emb, PHRASE_EMBEDDINGS)[0]
    best_idx = scores.argmax().item()
    best_score = float(scores[best_idx])

    if best_score > 0.50:
        cmd_key = INTENT_MAP[best_idx]
        intent_data = INTENTS_CONFIG[cmd_key]

        # Activate confirmation waiting state
        session["context"] = "awaiting_confirmation"
        session["pending_action"] = cmd_key

        conf_prompt = intent_data.get("confirmation_prompt", f"Do you want to execute {cmd_key}?")
        logger.info(f"🔒 Intent detected: {cmd_key}. Requesting confirmation...")

        audio_wav = generate_piper_tts_bytes(conf_prompt)
        headers = {
            "X-Server-Status": "awaiting_confirmation",
            "X-Transcription": sanitize_header(conf_prompt),
            "X-Requires-Followup": "true",
            "X-Cmd-Output": sanitize_header(conf_prompt)
        }
        return Response(content=audio_wav, media_type="audio/wav", headers=headers)

    # If intent is not understood
    unknown_msg = "I did not understand what you wanted me to do."
    logger.warning(f"Unrecognized intent from transcription: '{transcription}'")
    audio_wav = generate_piper_tts_bytes(unknown_msg)
    headers = {
        "X-Server-Status": "unknown_intent",
        "X-Transcription": sanitize_header(unknown_msg),
        "X-Requires-Followup": "false",
        "X-Cmd-Output": "Command not recognized."
    }
    return Response(content=audio_wav, media_type="audio/wav", headers=headers)

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Voice Commander API Server on port 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
