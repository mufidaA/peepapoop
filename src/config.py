from openai import OpenAI
import os

from dotenv import load_dotenv

load_dotenv()

AP_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI()
MODEL_ID = "gpt-5-chat-latest"
