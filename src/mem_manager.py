import logging
import os
import sys
from typing import Literal
from uuid import uuid4

from dotenv import load_dotenv
from langchain.agents import AgentType, initialize_agent
from langchain_core.documents import Document
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_postgres.vectorstores import PGVector

from src.config import client, logger
from langchain_core.runnables import RunnableLambda

DB_CONNECTION = os.getenv("DB_CONNECTION_STR")

LLM = ChatOpenAI(model="gpt-4o-mini", max_tokens=1024)

Embeddings = OpenAIEmbeddings(model="text-embedding-3-small")


VectorStore = PGVector(
    embeddings=Embeddings,
    collection_name="docs_demo",
    connection=DB_CONNECTION,
    use_jsonb=True,            # recommended
    create_extension=True,     # ensure vector extension is present
)


@tool
def manage_memory(
    operation: Literal["read", "write"],
    document: str,
    k: int = 5,
):
    """
    Interact with the memory.

    Args:
        operation: "write" to store a new memory, "read" to retrieve similar ones.
        document: For "write": the text to store. For "read": the query text.
        k: (read only) number of similar results to return. Defaults to 5.

    Returns:
        If writing: a dict with status and unique memory ID.
        If reading: a dict with status and a list of matching documents + scores.
    """
    if operation == "write":
        ts = uuid4().hex
        docs = [Document(page_content=document, metadata={"id": ts})]
        VectorStore.add_documents(docs)
        return {"status": "ok", "message": "memory written successfully", "id": ts}

    # read
    results = VectorStore.similarity_search_with_score(document, k=k)
    matches = [
        {"content": d.page_content, "metadata": d.metadata, "score": float(score)}
        for d, score in results
    ]
    return {"matches": matches}

def _read_from_memory(
    document: str,
    top_k: int = 5,
):
    """
    Read your memories for related context.

    Args:
        document: the topic to search
        k: number of similar results to return. Defaults to 5.

    Returns:
        a dict with status and a list of matching documents + scores.
    """

    results = VectorStore.similarity_search_with_score(document, k=top_k)
    matches = [
        {"content": d.page_content, "metadata": d.metadata, "score": float(score)}
        for d, score in results
    ]
    return {"Context from memory": matches}

@tool
def write_to_memory(
    document: str,
):
    """
    store a new valuable or user specific memory

    Args:
        document: summary of the information to store.
        k: (read only) number of similar results to return. Defaults to 5.

    Returns:
        If writing: a dict with status and unique memory ID.
    """
    ts = uuid4().hex
    docs = [Document(page_content=document, metadata={"id": ts})]
    VectorStore.add_documents(docs)
    return {"status": "ok", "message": "memory written successfully", "id": ts}

read_runnable = RunnableLambda(_read_from_memory)
read_from_memory = read_runnable.as_tool(
    name="read_from_memory",
    description="Read your memories for related context.",
    arg_types={"docuement": str, "top_k": int},
)


ReadMemoryAgent= initialize_agent(
    tools=[read_from_memory],
    llm=LLM,
    agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True,
)

MemoryAgent= initialize_agent(
    tools=[write_to_memory, read_from_memory],
    llm=LLM,
    agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True,
)