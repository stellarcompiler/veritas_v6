import os
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Logger Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("VERITAS")

# Configuration Constants
class Config:
    # AI Models
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    GOOGLE_API_KEY2 = os.getenv("GOOGLE_API_KEY2")
    GOOGLE_API_KEY3 = os.getenv("GOOGLE_API_KEY3")
    GOOGLE_API_KEY4= os.getenv("GOOGLE_API_KEYS4")
    MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:1b")
    VERBOSE_STATE = os.getenv("VERBOSE_STATE", "False")
    
    # NLP
    SPACY_MODEL = "en_core_web_lg"

    # Search
    SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    
    # CrewAI Memory Configuration
    MEMORY_TYPE = "short_term"  # short_term, long_term, entity, or combination
    ENABLE_MEMORY = False

    @staticmethod
    def validate():
        """Validate required environment variables."""
        errors = []
        
        if not Config.GOOGLE_API_KEY:
            errors.append("GOOGLE_API_KEY is missing in environment variables.")
        
        if not Config.SERPAPI_API_KEY:
            errors.append("SERPAPI_API_KEY is missing. Search tools will fail.")
        
        if errors:
            for error in errors:
                logger.error(error)
            raise EnvironmentError(f"Configuration validation failed: {', '.join(errors)}")
        
        logger.info("Configuration validated successfully.")
