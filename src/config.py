from openai import OpenAI
import os

from dotenv import load_dotenv
import logging, sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)

logger = logging.getLogger("src")

load_dotenv()

AP_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI()
MODEL_ID = "gpt-5-chat-latest"
