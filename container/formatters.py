import logging
import textwrap

# Configure module-level logger
logger = logging.getLogger(__name__)

def format_memory_status(text: str) -> str:
    """Formats the 'free -h' command output into a clean, single line for displays or TTS."""
    if not text:
        logger.warning("format_memory_status received empty input.")
        return ""
        
    try:
        lines = text.strip().split("\n")
        if len(lines) < 3:
            logger.debug("Memory output has fewer than 3 lines; falling back to basic sanitization.")
            return text.replace("\n", " ")
        
        mem_parts = lines[1].split()
        swap_parts = lines[2].split()
        
        mem_total = mem_parts[1] if len(mem_parts) > 1 else "?"
        mem_used = mem_parts[2] if len(mem_parts) > 2 else "?"
        mem_free = mem_parts[3] if len(mem_parts) > 3 else "?"
        
        swap_total = swap_parts[1] if len(swap_parts) > 1 else "?"
        swap_used = swap_parts[2] if len(swap_parts) > 2 else "?"
        
        # Build compact single-line layout
        formatted = f"RAM:{mem_used}/{mem_total} | Lib:{mem_free} | SWAP:{swap_used}"
        logger.debug("Successfully formatted memory status.")
        return formatted
        
    except Exception as e:
        logger.error(f"Error parsing memory status output: {e}")
        return text.strip().replace("\n", " ")

def format_disk_space(text: str) -> str:
    """Formats the 'df -h' command output into a compact single line."""
    if not text:
        logger.warning("format_disk_space received empty input.")
        return ""
        
    try:
        lines = text.strip().split("\n")
        if len(lines) < 2:
            logger.debug("Disk space output has fewer than 2 lines; falling back to basic sanitization.")
            return text.replace("\n", " ")
        
        # Look for root or home partitions
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 6 and (parts[5] == "/" or "/home" in parts[5]):
                size, used, avail, use_pct = parts[1], parts[2], parts[3], parts[4]
                logger.debug(f"Successfully formatted disk space for partition: {parts[5]}")
                return f"DISK ({parts[5]}): {used}/{size} ({use_pct})"
                
        # Fallback to the first available partition
        parts = lines[1].split()
        if len(parts) >= 5:
            logger.debug("Using fallback partition format for disk space.")
            return f"DISK: {parts[2]}/{parts[1]} ({parts[4]})"
            
        return text.replace("\n", " ")
        
    except Exception as e:
        logger.error(f"Error parsing disk space output: {e}")
        return text.strip().replace("\n", " ")

def sanitize_header(text: str) -> str:
    """Generic helper function to sanitize text intended for HTTP headers."""
    if not text:
        return ""
    return str(text).replace("\n", " ").replace("\r", " ").replace("\t", " ")
