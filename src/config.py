import logging
import os
import sys
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from langchain.agents import AgentType, initialize_agent
from langchain_core.documents import Document
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_postgres.vectorstores import PGVector
from openai import OpenAI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)

logger = logging.getLogger("src")

load_dotenv()
MODEL_ID = "gpt-5-chat-latest"
AP_KEY = os.getenv("OPENAI_API_KEY")
DB_CONNECTION = os.getenv("DB_CONNECTION_STR")

client = OpenAI()

LLM = ChatOpenAI(model="MODEL_ID", max_tokens=1024)


NOW = datetime.now(ZoneInfo("Europe/Helsinki"))

