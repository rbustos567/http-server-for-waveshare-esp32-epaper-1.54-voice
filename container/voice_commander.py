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

#MODEL_PATH = os.getenv("VOSK_MODEL_PATH", "/app/models/vosk-en")
CONFIG_PATH = "config.json"

HOST_RUNNER_URL = os.getenv("HOST_RUNNER_URL", "http://host.docker.internal:8001")
HOST_API_TOKEN = os.getenv("HOST_API_TOKEN", "my_secure_voice_token_123")

#if not os.path.exists(MODEL_PATH):
#    logger.critical(f"Vosk model not found at path: {MODEL_PATH}")
#    raise FileNotFoundError(f"Vosk model not found at {MODEL_PATH}")

#logger.info(f"Loading Vosk model from {MODEL_PATH}...")
#vosk_model = Model(MODEL_PATH)

CONFIG_PATH = "config.json"
with open(CONFIG_PATH, "r") as f:
    config_data = json.load(f)

PIPER_MODEL_PATH = config_data.get("piper_voice_model", "/app/voices/en-US-lessac-high.onnx")
PIPER_BINARY = config_data.get("piper_binary", "piper")
VOSK_MODEL_PATH = config_data.get("vosk_model_path", "/app/models/vosk-en")
logger.info(f"Vosk model not found at path: {VOSK_MODEL_PATH}")
VOSK_MODEL = Model(VOSK_MODEL_PATH)

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
    Generates raw binary WAV audio bytes using Piper TTS engine from text input securely,
    using the dynamic model path specified in config.json.
    """
    output_file = "/tmp/response.wav"
    input_file = "/tmp/input_text.txt"
    
    # Usa la ruta del modelo definida en config.json
    model_path = PIPER_MODEL_PATH  
    
    if not os.path.exists(model_path):
        logger.error(f"CRITICAL: Piper TTS model file not found at '{model_path}'!")
        return b""

    try:
        with open(input_file, "w", encoding="utf-8") as f:
            f.write(text)

        cmd = f"{PIPER_BINARY} --model {model_path} --output_file {output_file} < {input_file}"
        
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"Piper execution failed (exit code {result.returncode}): {result.stderr.strip()}")
            return b""

        if not os.path.exists(output_file):
            logger.error("Piper finished but output WAV file was not created.")
            return b""

        with open(output_file, "rb") as f:
            return f.read()
            
    except Exception as e:
        logger.error(f"Exception occurred while generating Piper TTS audio: {e}")
        return b""

def transcribe_wav(audio_bytes: bytes) -> str:
    """
    Transcribes raw audio bytes into text using the Vosk offline speech recognition engine.
    """
    recognizer = KaldiRecognizer(VOSK_MODEL, 16000)
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
    handling direct execution, confirmation workflows, and dynamic prompt inputs with formatters.
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

    # --- 1. HANDLE ACTIVE SESSION CONTEXTS ---

    # A) Awaiting Confirmation for a Direct Command
    if session["context"] == "awaiting_confirmation":
        pending_cmd = session["pending_action"]
        session["context"] = None
        session["pending_action"] = None

        valid_confirmation_words = config_data.get("settings", {}).get(
            "confirmation_words", ["sure", "ok"]
        )

        logger.info(f"🔍 DEBUG -> Palabras válidas cargadas: {valid_confirmation_words} | Transcripción recibida: '{text_lower}'")

        if any(w in text_lower for w in valid_confirmation_words):
            logger.info(f"✅ Confirmation accepted for direct command: {pending_cmd}")
            exec_params = {} # Direct commands have no dynamic arguments
            
            # --- COMMON EXECUTION & FORMATTING BLOCK ---
            exec_res = call_host_broker(pending_cmd, params=exec_params)
            intent_data = INTENTS_CONFIG.get(pending_cmd, {})
            success_msg = intent_data.get("success_message", "Command executed successfully.")
            host_output = exec_res.get("output", "")
            cmd_out = host_output if (host_output and host_output.strip() != "") else success_msg

            # 1. Apply Formatter
            formatter_name = intent_data.get("formatter")
            if formatter_name and hasattr(formatters, formatter_name):
                formatter_func = getattr(formatters, formatter_name)
                cmd_out_header = str(formatter_func(cmd_out)).replace("\n", " ").replace("\r", "")
            else:
                cmd_out_header = sanitize_header(cmd_out)

            # 2. Determine Speech Payload (TTS Output Config)
            should_speak_output = intent_data.get("tts_output", False)
            speech_text = cmd_out_header if should_speak_output else success_msg

            logger.info(f"🔊 Generating TTS audio (speaking output: {should_speak_output})")
            audio_wav = generate_piper_tts_bytes(speech_text)
            headers = {
                "X-Server-Status": "success",
                "X-Transcription": sanitize_header(success_msg),
                "X-Requires-Followup": "false",
                "X-Cmd-Output": cmd_out_header
            }
            return Response(content=audio_wav, media_type="audio/wav", headers=headers)
        else:
            logger.info("❌ Action cancelled by user.")
            cancel_msg = config_data.get("settings", {}).get("cancel_message", "Action cancelled.")
            audio_wav = generate_piper_tts_bytes(cancel_msg)
            headers = {
                "X-Server-Status": "cancelled",
                "X-Transcription": sanitize_header(cancel_msg),
                "X-Requires-Followup": "false",
                "X-Cmd-Output": sanitize_header(cancel_msg)
            }
            return Response(content=audio_wav, media_type="audio/wav", headers=headers)

    # B) Awaiting Dynamic Prompt Input (Captures voice as <argument>)
    elif session["context"] == "awaiting_prompt":
        pending_cmd = session["pending_action"]
        session["context"] = None
        session["pending_action"] = None

        user_argument = transcription
        logger.info(f"🤖 Executing prompt_input command '{pending_cmd}' with argument: '{user_argument}'")
        exec_params = {"argument": user_argument}

        # --- COMMON EXECUTION & FORMATTING BLOCK ---
        exec_res = call_host_broker(pending_cmd, params=exec_params)
        intent_data = INTENTS_CONFIG.get(pending_cmd, {})
        success_msg = intent_data.get("success_message", "Command executed successfully.")
        host_output = exec_res.get("output", "")
        cmd_out = host_output if (host_output and host_output.strip() != "") else success_msg

        # 1. Apply Formatter
        formatter_name = intent_data.get("formatter")
        if formatter_name and hasattr(formatters, formatter_name):
            formatter_func = getattr(formatters, formatter_name)
            cmd_out_header = str(formatter_func(cmd_out)).replace("\n", " ").replace("\r", "")
        else:
            cmd_out_header = sanitize_header(cmd_out)

        # 2. Determine Speech Payload (TTS Output Config)
        should_speak_output = intent_data.get("tts_output", False)
        speech_text = cmd_out_header if should_speak_output else success_msg

        logger.info(f"🔊 Generating TTS audio (speaking output: {should_speak_output})")
        audio_wav = generate_piper_tts_bytes(speech_text)
        headers = {
            "X-Server-Status": "success",
            "X-Transcription": sanitize_header(success_msg),
            "X-Requires-Followup": "false",
            "X-Cmd-Output": cmd_out_header
        }
        return Response(content=audio_wav, media_type="audio/wav", headers=headers)

    # --- 2. MATCH NEW INTENT FROM TRANSCRIPTION ---
    user_emb = nlp_model.encode(transcription, convert_to_tensor=True)
    scores = util.cos_sim(user_emb, PHRASE_EMBEDDINGS)[0]
    best_idx = scores.argmax().item()
    best_score = float(scores[best_idx])

    if best_score > 0.50:
        cmd_key = INTENT_MAP[best_idx]
        intent_data = INTENTS_CONFIG[cmd_key]
        
        cmd_type = intent_data.get("type", "direct")
        requires_conf = intent_data.get("requires_confirmation", True)

        # CASE 1: Command requires a dynamic prompt input (e.g. Ollama with <argument>)
        if cmd_type == "prompt_input":
            session["context"] = "awaiting_prompt"
            session["pending_action"] = cmd_key
            
            prompt_msg = intent_data.get("confirmation_prompt", "What do you want to ask?")
            logger.info(f"🎙️ Prompt-input intent detected: {cmd_key}. Requesting argument...")

            audio_wav = generate_piper_tts_bytes(prompt_msg)
            headers = {
                "X-Server-Status": "awaiting_prompt",
                "X-Transcription": sanitize_header(prompt_msg),
                "X-Requires-Followup": "true",
                "X-Cmd-Output": sanitize_header(prompt_msg)
            }
            return Response(content=audio_wav, media_type="audio/wav", headers=headers)

        # CASE 2: Direct Command WITH Confirmation Required
        elif cmd_type == "direct" and requires_conf:
            session["context"] = "awaiting_confirmation"
            session["pending_action"] = cmd_key

            conf_prompt = intent_data.get("confirmation_prompt", f"Do you want to execute {cmd_key}?")
            logger.info(f"🔒 Direct intent with confirmation detected: {cmd_key}.")

            audio_wav = generate_piper_tts_bytes(conf_prompt)
            headers = {
                "X-Server-Status": "awaiting_confirmation",
                "X-Transcription": sanitize_header(conf_prompt),
                "X-Requires-Followup": "true",
                "X-Cmd-Output": sanitize_header(conf_prompt)
            }
            return Response(content=audio_wav, media_type="audio/wav", headers=headers)

        # CASE 3: Direct Command WITHOUT Confirmation (Execute immediately)
        elif cmd_type == "direct" and not requires_conf:
            logger.info(f"⚡ Direct intent without confirmation. Executing immediately: {cmd_key}")
            exec_params = {}

            # --- COMMON EXECUTION & FORMATTING BLOCK ---
            exec_res = call_host_broker(cmd_key, params=exec_params)
            success_msg = intent_data.get("success_message", "Command executed successfully.")
            host_output = exec_res.get("output", "")
            cmd_out = host_output if (host_output and host_output.strip() != "") else success_msg

            formatter_name = intent_data.get("formatter")
            if formatter_name and hasattr(formatters, formatter_name):
                formatter_func = getattr(formatters, formatter_name)
                cmd_out_header = str(formatter_func(cmd_out)).replace("\n", " ").replace("\r", "")
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

    # --- 3. UNKNOWN INTENT FALLBACK ---
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
