import re

from src.config import MODEL_ID, NOW, client, logger
from src.mem_manager import MemoryAgent, ReadMemoryAgent, _read_from_memory
from src.spells import pipa_core, remember_read, remember_write
from src.transcribe import transcribe_with_identify
from typing import Optional, Callable
import threading  # NEW: use a background thread for the write


def persist_interaction_memory(interaction: str):
    """Background task: write the interaction to memory safely."""
    try:
        # Use the imported remember_write spell (not memory_spell)
        MemoryAgent.invoke(remember_write.format(payload=interaction))
    except Exception as e:
        logger.exception(f"background memory write failed: {e}")

async def awake_mode(wav_buf: bytes, on_chunk: Optional[Callable[[str], object]] = None) -> Optional[str]:
    try:
        # 1) Speech-to-text (+ identity)
        identity, text = transcribe_with_identify(wav_buf)
        input_text = (identity + (text or "").strip()).strip()

        from_mem = _read_from_memory(document=input_text, top_k=10)
        #ReadMemoryAgent.invoke(remember_read.format(payload=input_text))
        logger.info("Context form mem %s", from_mem)

        if not text or not text.strip():
            logger.info("empty capture.")
            return None

        # 2) LLM reply
        stream = client.chat.completions.create(
            model=MODEL_ID,
            stream=True,
            messages=[
                {"role": "system", "content": pipa_core.format(now=NOW, memories=from_mem)},
                {"role": "user", "content": input_text},
            ],
        )

        full = []
        text_buffer = ""
        sentence_end = re.compile(r"([.!?])")
        # iterate streaming deltas
        for event in stream:
            # OpenAI Chat Completions stream shape: choices[0].delta.content
            delta = getattr(event.choices[0].delta, "content", None)
            if delta:
                full.append(delta)
                text_buffer += delta
                while True:
                    match = sentence_end.search(text_buffer)
                    if not match:
                        break
                    end_idx = match.end()
                    sentence = text_buffer[:end_idx]
                    text_buffer = text_buffer[end_idx:]
                    if on_chunk:
                        logger.info(f"emitting chunk: {sentence}")
                        await on_chunk(sentence)

        if text_buffer and on_chunk:
            await on_chunk(text_buffer)

        text_response = "".join(full) if full else ""

        # 3) Persist memory in the background WITHOUT asyncio (we're in a worker thread)
        interaction = f"{input_text}\n\n System Response: {text_response}"
        threading.Thread(
            target=persist_interaction_memory, args=(interaction,), daemon=True
        ).start()

    except Exception as e:
        logger.exception(f"awake_mode error: {e}")
        return None
