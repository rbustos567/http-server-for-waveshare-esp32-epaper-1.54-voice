{
  "vosk_model_path": "/app/models/vosk-es",
  "piper_voice_model": "voices/es_MX-claude-high.onnx",
  "piper_binary": "/usr/local/bin/piper",
  "settings": {
    "confirmation_words": ["si", "sí", "hazlo", "confirmo"],
    "cancel_message": "Accion cancelada.",
    "unknown_message": "No entendí lo que querías que hiciera."
  },
  "commands": {
    "check_ram": {
      "phrases": ["checar ram", "uso de memoria", "cuanta memoria tengo", "uso de ram"],
      "formatter": "format_memory_status",
      "confirmation_prompt": "¿Deseas checar la memoria RAM del sistema?",
      "success_message": "Aqui esta el reporte de memoria RAM",
      "requires_confirmation": true,
      "tts_output": false
    },
    "check_disk_space": {
      "phrases": ["checar espacio de disco", "checar disco", "espacio de disco"],
      "command": "df -h",
      "formatter": "format_disk_space",
      "confirmation_prompt": "¿Deseas checar el espacio de disco del sistema?",
      "success_message": "Aqui esta el reporte de espacio de disco",
      "requires_confirmation": true,
      "tts_output": false
    },
    "update_epaper_screen_w_random_info": {
      "phrases": ["actualizar informacion en pantalla e paper", "Actualizar pantalla e paper con info aleatoria"],
      "command": "ssh pi@192.168.1.12 '/home/pi/git/projects/waveshare-eink-pi-zero-photo-frame/run_on_cron_display_on_eink.sh info'",
      "confirmation_prompt": "¿Deseas actualizar la pantalla e paper con informacion aleatoria?",
      "success_message": "He actualizado la pantalla e paper con informacion aleatoria",
      "requires_confirmation": true,
      "tts_output": false
    },
    "update_epaper_screen_w_random_photo": {
      "phrases": ["Actualizar foto en pantalla e paper", "Actualizar pantalla e paper con foto aleatoria"],
      "command": "ssh pi@192.168.1.12 '/home/pi/git/projects/waveshare-eink-pi-zero-photo-frame/run_on_cron_display_on_eink.sh photo'",
      "confirmation_prompt": "¿Deseas actualizar la pantalla e paper con una foto aleatoria?",
      "success_message": "He actualizado la pantalla e paper con una foto aleatoria",
      "requires_confirmation": true,
      "tts_output": false
    },
    "ask_local_ai_text": {
      "type": "prompt_input",
      "phrases": ["Preguntar a agente local de inteligencia artificial", "Preguntar a inteligencia artificial"],
      "command": "ollama run gemma2:2b <argument>? Responde en un enunciado",
      "formatter": "format_ollama_response",
      "confirmation_prompt": "¿Qué deseas preguntarle al agente local de inteligencia artificial?",
      "success_message": "Aqui esta la respuesta del agente local",
      "requires_confirmation": false,
      "tts_output": true
    }
  }
}
