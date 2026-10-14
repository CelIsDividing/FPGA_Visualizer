import os
from dataclasses import dataclass

@dataclass
class Settings:
    # Putanje
    UPLOAD_FOLDER = "uploads"
    OUTPUT_FOLDER = "output"
    STATIC_FOLDER = "static"
    
    # Vizuelizacija
    CELL_SIZE = 100  # Increased from 50 for better visibility
    CANVAS_PADDING = 100
    SIGNAL_COLORS = ['red', 'green', 'blue', 'magenta', 'cyan', 'orange']
    
    # Analiza
    CONGESTION_THRESHOLD = 0.8
    HUB_CENTRALITY_THRESHOLD = 0.1
    
    # Web server (env vars override defaults so hosting platforms can inject PORT)
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = int(os.environ.get("PORT", "5000"))
    DEBUG = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")

settings = Settings()

# Kreiranje direktorijuma ako ne postoje
os.makedirs(settings.UPLOAD_FOLDER, exist_ok=True)
os.makedirs(settings.OUTPUT_FOLDER, exist_ok=True)