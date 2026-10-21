import time
import requests
import sounddevice as sd
import scipy.io.wavfile as wav

SERVER_URL = "http://localhost:8000/process-audio"
SAMPLE_RATE = 16000
DURATION = 4  # Duración de grabación por instrucción

def record_and_send():
    print("\n🎙 Speak now (Recording for 4 seconds)...")
    audio_data = sd.rec(int(DURATION * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='int16')
    sd.wait()

    wav.write("/tmp/temp_input.wav", SAMPLE_RATE, audio_data)

    with open("/tmp/temp_input.wav", "rb") as f:
        files = {"file": ("audio.wav", f, "audio/wav")}
        data = {"session_id": "fedora_cli_user"}
        try:
            response = requests.post(SERVER_URL, files=files, data=data, timeout=15)
            res_json = response.json()
            
            print(f"\n🗣 You said: \"{res_json.get('transcription')}\"")
            print(f"🤖 Assistant: {res_json.get('display_text')}")
            
            if res_json.get("host_output"):
                print(f"🖥 Host Output:\n{res_json.get('host_output')}")
            
            # Si requiere seguimiento (confirmación o selección), graba automáticamente de nuevo
            if res_json.get("requires_followup"):
                print("\n🔁 Action requires follow-up...")
                time.sleep(1)
                record_and_send()

        except Exception as e:
            print(f"❌ Error connecting to server: {e}")

if __name__ == "__main__":
    record_and_send()
