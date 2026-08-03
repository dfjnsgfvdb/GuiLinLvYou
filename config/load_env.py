import logging
import logging.config
import os

from dotenv import load_dotenv


def load_env():
    """Load logging and the local development environment."""
    os.makedirs("logs", exist_ok=True)
    with open("config/logging.conf", encoding="utf-8") as file:
        logging.config.fileConfig(file)

    environment = os.getenv("ENV", "dev")
    local_path = ".env.local"
    environment_path = f".env.{environment}"
    dotenv_path = local_path if os.path.exists(local_path) else environment_path
    logging.info("Loading environment configuration from %s", dotenv_path)
    load_dotenv(dotenv_path)
