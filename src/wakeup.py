from config import client, logger
import json
import numpy as np


OPENAI_ENGINE = "text-embedding-3-small"


def wakeup_bank(path: str = "wake_up.json") -> list[str]:
    """
    get json dict that contains the wakeup sentences and their embd.
    return list of embd items.
    """
    with open(path, "r", encoding="utf-8") as f:
        wake_up_dict = json.load(f)
    return list(wake_up_dict.values())


def embed(text):
    response = client.embeddings.create(
        input=text, model=OPENAI_ENGINE
    )  # dimensions=1024
    return response.data[0].embedding


def cosine_similarity(a, b):
    """Compute cosine similarity between two vectors."""
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def is_wake_phrase(text: str, threshold: float = 0.85) -> bool:
    """
    Check if `text` is similar to any stored wake phrase.
    Returns True if similarity is above `threshold`.
    """
    logger.info("embedding: %s", text)
    embd_input = embed(text)
    bank = wakeup_bank()  # list of embeddings from your JSON

    for embd in bank:
        sim = cosine_similarity(embd_input, embd)
        if sim >= threshold:
            logger.info("matches wakeup with sim: %s", sim)
            return True
    return False
