import os
import logging
from pathlib import Path
from typing import List, Dict, Optional

class ConfigLoader:
    """
    Explicit, validated configuration management for SummitOS.
    Aligns with schema-first architecture by ensuring explicit state.
    """
    REQUIRED_KEYS = [
        "AZURE_VISION_ENDPOINT",
        "OPENAI_API_KEY",
        "SQL_CONNECTION_STRING"
    ]

    def __init__(self, env_path: Optional[Path] = None):
        self.base_dir = Path(__file__).resolve().parents[1]
        self.env_path = env_path or (self.base_dir / "config" / ".env")
        self.config: Dict[str, str] = {}

    def load(self, inject_to_os: bool = True) -> Dict[str, str]:
        """Loads and validates environment variables."""
        if not self.env_path.exists():
            logging.warning(f"ConfigLoader: .env not found at {self.env_path}")
        else:
            with open(self.env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        name, value = line.split('=', 1)
                        # Remove quotes if present
                        value = value.strip('"').strip("'")
                        self.config[name] = value

        if inject_to_os:
            for k, v in self.config.items():
                os.environ[k] = v
                
        self.validate()
        return self.config

    def validate(self):
        """Early-failure assertion for required keys."""
        missing = [k for k in self.REQUIRED_KEYS if not os.environ.get(k)]
        if missing:
            raise RuntimeError(f"ConfigLoader Error: Missing required environment variables: {missing}")
        logging.info("ConfigLoader: Environment readiness verified.")

# Singleton instance for easy import
config_loader = ConfigLoader()
