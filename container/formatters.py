import textwrap

def format_memory_status(text: str) -> str:
    """Formatea la salida de 'free -h' en una sola línea limpia para la e-Paper."""
    try:
        lines = text.strip().split("\n")
        if len(lines) < 3:
            return text.replace("\n", " ")
        
        mem_parts = lines[1].split()
        swap_parts = lines[2].split()
        
        mem_total = mem_parts[1] if len(mem_parts) > 1 else "?"
        mem_used = mem_parts[2] if len(mem_parts) > 2 else "?"
        mem_free = mem_parts[3] if len(mem_parts) > 3 else "?"
        
        swap_total = swap_parts[1] if len(swap_parts) > 1 else "?"
        swap_used = swap_parts[2] if len(swap_parts) > 2 else "?"
        
        # Diseño compacto de una sola línea
        return f"RAM:{mem_used}/{mem_total} | Lib:{mem_free} | SWAP:{swap_used}"
    except Exception:
        return text.strip().replace("\n", " ")

def format_disk_space(text: str) -> str:
    """Formatea la salida de 'df -h' en una sola línea compacta."""
    try:
        lines = text.strip().split("\n")
        if len(lines) < 2:
            return text.replace("\n", " ")
        
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 6 and (parts[5] == "/" or "/home" in parts[5]):
                size, used, avail, use_pct = parts[1], parts[2], parts[3], parts[4]
                return f"DISK ({parts[5]}): {used}/{size} ({use_pct})"
                
        # Fallback a la primera partición
        parts = lines[1].split()
        if len(parts) >= 5:
            return f"DISK: {parts[2]}/{parts[1]} ({parts[4]})"
            
        return text.replace("\n", " ")
    except Exception:
        return text.strip().replace("\n", " ")

def sanitize_header(text: str) -> str:
    """Función auxiliar genérica para limpiar textos destinados a headers HTTP."""
    if not text:
        return ""
    return str(text).replace("\n", " ").replace("\r", " ").replace("\t", " ")
