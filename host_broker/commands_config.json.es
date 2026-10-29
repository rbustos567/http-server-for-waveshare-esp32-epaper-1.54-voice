{
  "check_ram": {
    "description": "Check available system RAM",
    "command": "free -h"
  },
  "check_disk_space": {
    "description": "Check system disk space",
    "command": "df -h"
  },
  "update_epaper_screen_w_random_info": {
    "description": "Update e-paper screen with random information",
    "command": "ssh pi@192.168.1.12 '/home/pi/git/projects/waveshare-eink-pi-zero-photo-frame/run_on_cron_display_on_eink.sh info'"
  },
  "update_epaper_screen_w_random_photo": {
    "description": "Update e-paper screen with random photo",
    "command": "ssh pi@192.168.1.12 '/home/pi/git/projects/waveshare-eink-pi-zero-photo-frame/run_on_cron_display_on_eink.sh photo'"
  },
  "ask_local_ai_text": {
     "description": "Ask a question to local Ollama model",
     "command": "ollama run gemma2:2b <argument>? Responde en un enunciado." 
  }
}
