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

# Session timeout in seconds
SESSION_TIMEOUT = 60

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

CONFIG_PATH = "config.json"

HOST_RUNNER_URL = os.getenv("HOST_RUNNER_URL", "http://host.docker.internal:8001")
HOST_API_TOKEN = os.getenv("HOST_API_TOKEN", "my_secure_voice_token_123")

CONFIG_PATH = "config.json"
with open(CONFIG_PATH, "r") as f:
    config_data = json.load(f)

PIPER_MODEL_PATH = config_data.get("piper_voice_model", "/app/voices/en-US-lessac-high.onnx")
PIPER_BINARY = config_data.get("piper_binary", "piper")
DEFAULT_VOSK_PATH = config_data.get("vosk_model_path", "/app/models/vosk-en")

# Cache dictionary to store loaded Vosk models in memory
VOSK_MODELS_CACHE = {
    "default": Model(DEFAULT_VOSK_PATH)
}

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
    # Clean whitespace characters first
    cleaned = str(text).replace("\n", " ").replace("\r", " ").replace("\t", " ")
    # Strip characters that latin-1 headers cannot encode
    return cleaned.encode("ascii", "ignore").decode("ascii")

def get_vosk_model(model_path: str):
    """Load and cache Vosk models dynamically based on the provided path."""
    if not model_path:
        logger.info("DEBUG ---> get_vosk_model: No path provided, falling back to default.")
        return VOSK_MODELS_CACHE["default"]
    
    if model_path not in VOSK_MODELS_CACHE:
        logger.info(f"Loading alternative Vosk model: {model_path}")
        VOSK_MODELS_CACHE[model_path] = Model(model_path)
    else:
        logger.info(f"DEBUG ---> get_vosk_model: Reusing cached model for path: {model_path}")
        
    return VOSK_MODELS_CACHE[model_path]

def get_session(session_id: str):
    """
    Retrieves or initializes an active user session state based on session_id.
    Automatically expires and resets sessions inactive for more than SESSION_TIMEOUT seconds.
    """
    now = time.time()
    if session_id not in SESSIONS or (now - SESSIONS[session_id]["timestamp"]) > SESSION_TIMEOUT:
        logger.info(f"Creating or resetting session state for ID: {session_id}")
        SESSIONS[session_id] = {
            "context": None,
            "pending_action": None,
            "pending_options": {},
            "selection_action": None,
            "followup_action": None,
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

def transcribe_wav(audio_bytes: bytes, vosk_model) -> str:
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
        res = requests.post(f"{HOST_RUNNER_URL}/exec", json=payload, headers=headers, timeout=300)
        return res.json()
    except Exception as e:
        logger.error(f"Failed to communicate with host runner broker: {e}")
        return {"status": "error", "output": str(e)}

# --- STATE HANDLERS (Modular State Machine) ---

def handle_idle_state(session, transcription, text_lower, intent_data, cmd_key):
    """Handles commands received in idle state (direct or prompt_input)."""
    cmd_type = intent_data.get("type", "direct")
    requires_conf = intent_data.get("requires_confirmation", True)

    if cmd_type == "prompt_input":
        # Transition to awaiting_prompt state
        session["context"] = "awaiting_prompt"
        session["pending_action"] = cmd_key
        prompt_msg = intent_data.get("confirmation_prompt", "What do you want to ask?")
        return create_system_response("awaiting_prompt", prompt_msg, "true", prompt_msg)

    elif cmd_type == "direct" and requires_conf:
        # Transition to awaiting_confirmation state
        session["context"] = "awaiting_confirmation"
        session["pending_action"] = cmd_key
        conf_msg = intent_data.get("confirmation_prompt", f"Do you want to execute {cmd_key}?")
        return create_system_response("awaiting_confirmation", conf_msg, "true", conf_msg)

    else:
        # Execute direct command immediately without confirmation
        return execute_and_render_command(cmd_key, params={}, session=session)

def handle_awaiting_confirmation(session, transcription, text_lower):
    """Handles confirmation response for direct commands."""
    pending_cmd = session.get("pending_action")
    session["context"] = None
    session["pending_action"] = None

    valid_conf_words = config_data.get("settings", {}).get("confirmation_words", ["sure", "ok"])
    
    if any(w in text_lower for w in valid_conf_words):
        logger.info(f"Confirmation accepted for command: {pending_cmd}")
        return execute_and_render_command(pending_cmd, params={}, session=session)
    else:
        logger.info("Action cancelled by user.")
        cancel_msg = config_data.get("settings", {}).get("cancel_message", "Action cancelled.")
        return create_system_response("cancelled", cancel_msg, "false", cancel_msg)

def handle_awaiting_prompt(session, transcription, text_lower):
    """Handles dynamic argument input from speech."""
    pending_cmd = session.get("pending_action")
    session["context"] = None
    session["pending_action"] = None

    user_argument = transcription
    logger.info(f"Executing prompt_input command '{pending_cmd}' with argument: '{user_argument}'")
    
    exec_params = {"argument": user_argument}
    return execute_and_render_command(pending_cmd, params=exec_params, session=session)

def handle_awaiting_list_selection(session, transcription, text_lower):
    """Handles user selection from an indexed options list (e.g., torrents)."""
    selection_action = session.get("selection_action")
    options_map = session.get("pending_options", {})
    
    # Clear selection state
    session["context"] = None
    session["selection_action"] = None
    session["pending_options"] = {}

    # Extract number from speech (digits or words)
    import re
    match = re.search(r'\d+', text_lower)
    selected_key = match.group() if match else None
    
    if not selected_key:
        word_to_num = config_data.get("settings", {}).get("word_to_num", {
            "first": "1", "one": "1",
            "second": "2", "two": "2"
        })

        for word, num in word_to_num.items():
            if word in text_lower:
                selected_key = num
                break

    if selected_key and selected_key in options_map:
        chosen_value = options_map[selected_key]
        logger.info(f"Selection accepted: index '{selected_key}' -> value '{chosen_value}'")
        
        exec_params = {"argument": chosen_value}
        return execute_and_render_command(selection_action, params=exec_params, session=session)
    else:

        unknown_msg = config_data.get("settings", {}).get("unknown_message", "I did not understand what you wanted me to do.")
        logger.warning(f"Unrecognized intent from transcription: '{transcription}'")
        return create_system_response("unknown_intent", unknown_msg, "false", "Command not recognized.")

def create_system_response(status: str, transcription: str, requires_followup: str, cmd_output: str, audio_bytes: bytes = None):
    """Helper to build standardized FastAPI Responses for system messages or errors."""
    headers = {
        "X-Server-Status": status,
        "X-Transcription": sanitize_header(transcription),
        "X-Requires-Followup": requires_followup,
        "X-Cmd-Output": sanitize_header(cmd_output)
    }
    
    # If no pre-generated audio bytes are passed, generate TTS audio from transcription
    if audio_bytes is None:
        audio_bytes = generate_piper_tts_bytes(transcription if transcription else "Done")
        
    return Response(content=audio_bytes, media_type="audio/wav", headers=headers)

def process_incoming_audio(audio_bytes: bytes, vosk_model = None):
    """Transcribes audio bytes and handles empty speech edge cases."""
    if not audio_bytes:
        return None, "No audio or speech detected."
   
    # If no specific model is passed, fall back to the global default
    if vosk_model is None:
        vosk_model = VOSK_MODELS_CACHE["default"]

    transcription = transcribe_wav(audio_bytes, vosk_model)
    logger.info(f"Transcription received: '{transcription}'")
    
    if not transcription:
        return None, "No audio or speech detected."
        
    return transcription, None

def handle_prompt_input_intent(session, cmd_key, intent_data):
    """Handles commands requiring dynamic argument input from voice."""
    session["context"] = "awaiting_prompt"
    session["pending_action"] = cmd_key

    prompt_msg = intent_data.get("confirmation_prompt", "What do you want to ask?")
    logger.info(f"Prompt-input intent detected: {cmd_key}. Requesting argument...")
    
    return create_system_response("awaiting_prompt", prompt_msg, "true", prompt_msg)

def handle_confirmation_intent(session, cmd_key, intent_data):
    """Handles direct commands that require user confirmation before execution."""
    session["context"] = "awaiting_confirmation"
    session["pending_action"] = cmd_key
    
    conf_msg = intent_data.get("confirmation_prompt", f"Do you want to execute {cmd_key}?")
    logger.info(f"Direct intent with confirmation detected: {cmd_key}.")
    
    return create_system_response("awaiting_confirmation", conf_msg, "true", conf_msg)

def handle_immediate_execution_intent(session, cmd_key, intent_data):
    """Handles direct commands executed immediately without confirmation."""
    logger.info(f"Direct intent without confirmation. Executing immediately: {cmd_key}")
    
    return execute_and_render_command(cmd_key, params={}, session=session)

def handle_command_intent(session, cmd_key, intent_data):
    """Handles routing when a new intent is matched from speech in idle state."""
    cmd_type = intent_data.get("type", "direct")
    requires_conf = intent_data.get("requires_confirmation", True)
    
    # CASE 1: Command requires a dynamic prompt input (e.g. argument capture)
    if cmd_type == "prompt_input":
        return handle_prompt_input_intent(session, cmd_key, intent_data)
    # CASE 2: Direct Command WITH Confirmation Required
    elif cmd_type == "direct" and requires_conf:
        return handle_confirmation_intent(session, cmd_key, intent_data)
    # CASE 3: Direct Command WITHOUT Confirmation (Execute immediately)
    else:
        return handle_immediate_execution_intent(session, cmd_key, intent_data)

def execute_and_render_command(cmd_key: str, params: dict, session: dict):
    """Executes a command via host broker, applies formatters or indexed hash logic, and returns response."""
    exec_res = call_host_broker(cmd_key, params=params)
    logger.info(f"DEBUG HOST_RES -> {exec_res}")
    
    intent_data = INTENTS_CONFIG.get(cmd_key, {})
    success_msg = intent_data.get("success_message", "Command executed successfully.")
    host_output = exec_res.get("output", "")
    
    output_type = intent_data.get("output_type")
    requires_followup_header = "false"

    if output_type == "indexed_hash":
        # Handle interactive list options (e.g., torrent search)
        parsed_json = None
        try:
            if host_output and host_output.strip().startswith("{"):
                parsed_json = json.loads(host_output)
        except Exception:
            pass

        if parsed_json and isinstance(parsed_json, dict):
            display_text = sanitize_header(parsed_json.get("display_text", ""))
            session["pending_options"] = parsed_json.get("options", {})
            session["selection_action"] = intent_data.get("selection_action")
            session["context"] = "awaiting_list_selection"
            requires_followup_header = "true"
            
            cmd_out_header = f"{display_text} | {success_msg}"
        else:
            cmd_out_header = sanitize_header(host_output)
    else:
        # Standard text output handling
        cmd_out = host_output if (host_output and host_output.strip() != "") else success_msg

        formatter_name = intent_data.get("formatter")
        if formatter_name and hasattr(formatters, formatter_name):
            formatter_func = getattr(formatters, formatter_name)
            cmd_out_header = str(formatter_func(cmd_out)).replace("\n", " ").replace("\r", "")
        else:
            cmd_out_header = sanitize_header(cmd_out)

        # Check for followup next_action
        next_action = intent_data.get("next_action")
        if next_action:
            session["context"] = "awaiting_confirmation"
            session["pending_action"] = next_action
            requires_followup_header = "true"

            next_intent_data = INTENTS_CONFIG.get(next_action, {})
            followup_prompt = next_intent_data.get("confirmation_prompt", "Do you want to continue?")
            success_msg = f"{success_msg}. {followup_prompt}"
            cmd_out_header = f"{cmd_out_header} | {followup_prompt}"

    # Determine speech payload
    should_speak_output = intent_data.get("tts_output", False)
    speech_text = cmd_out_header if should_speak_output else success_msg

    logger.info(f"Generating TTS audio (speaking output: {should_speak_output})")
    audio_wav = generate_piper_tts_bytes(speech_text)

    return create_system_response(
        status="success",
        transcription=success_msg,
        requires_followup=requires_followup_header,
        cmd_output=cmd_out_header,
        audio_bytes=audio_wav
    )

@app.post("/process-audio", dependencies=[Depends(verify_api_key)])
async def process_audio(request: Request):
    """
    Main webhook endpoint processing incoming audio bytes from the ESP32 client,
    handling direct execution, confirmation workflows, and dynamic prompt inputs with formatters.
    """
    audio_bytes = await request.body()
    comm_status = request.headers.get("X-Communication-Status", "active")

    # Handle session close or empty buffer
    if comm_status == "final" or len(audio_bytes) == 0:
        logger.info("Session closed or empty audio buffer received.")
        return create_system_response("closed", "", "false", "Session closed.")

    # Initialize session and text normalizations
    session = get_session("default_session")
    current_context = session.get("context")
    pending_action = session.get("pending_action")

    # Determine which Vosk model to use based on pending command configuration
    target_vosk_path = None
    if current_context == "awaiting_prompt" and pending_action:
        intent_config = INTENTS_CONFIG.get(pending_action, {})
        logger.info(f"DEBUG ---> current_context = {current_context} | pending_action = {pending_action}")
        target_vosk_path = intent_config.get("vosk_model_path")
        logger.info(f"DEBUG ---> Target Vosk path retrieved: {target_vosk_path}")

    active_vosk_model = get_vosk_model(target_vosk_path)

    # Transcribe audio
    transcription, err_msg = process_incoming_audio(audio_bytes, active_vosk_model)
    if err_msg:
        logger.warning(err_msg)
        return create_system_response("ignored", "", "false", err_msg)
    
    text_lower = transcription.lower()

    # State Dispatcher (Route based on current session context)
    if current_context == "awaiting_confirmation":
        return handle_awaiting_confirmation(session, transcription, text_lower)
    elif current_context == "awaiting_prompt":
        return handle_awaiting_prompt(session, transcription, text_lower)
    elif current_context == "awaiting_list_selection":
        return handle_awaiting_list_selection(session, transcription, text_lower)

    # MATCH NEW INTENT FROM TRANSCRIPTION
    user_emb = nlp_model.encode(transcription, convert_to_tensor=True)
    scores = util.cos_sim(user_emb, PHRASE_EMBEDDINGS)[0]
    best_idx = scores.argmax().item()
    best_score = float(scores[best_idx])

    if best_score > 0.50:
        cmd_key = INTENT_MAP[best_idx]
        intent_data = INTENTS_CONFIG[cmd_key]
        return handle_command_intent(session, cmd_key, intent_data)

    # UNKNOWN INTENT FALLBACK
    unknown_msg = config_data.get("settings", {}).get("unknown_message", "I did not understand what you wanted me to do.")
    logger.warning(f"Unrecognized intent from transcription: '{transcription}'")
    return create_system_response("unknown_intent", unknown_msg, "false", "Command not recognized.")

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Voice Commander API Server on port 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
