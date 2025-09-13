from openai import OpenAI
import os
from src.spells import pipa_core
from pathlib import Path
from src.transcribe import transcribe_with_identify, record_until_silence
import pyaudio
from src.config import client, MODEL_ID, logger

from src.wakeup import is_wake_phrase
import time


def say_stream(text, voice="alloy", model="tts-1-hd"):
    # OpenAI TTS outputs 24 kHz, 16-bit mono when using response_format="pcm"
    RATE = 24000
    pa = pyaudio.PyAudio()
    stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE, output=True)

    with client.audio.speech.with_streaming_response.create(
        model=model,
        voice=voice,
        input=text,
        instructions="Speak in a cheerful and excitment tone.",
        response_format="pcm",  # raw 16-bit little-endian PCM
        # instructions="Speak in a cheerful and excitement tone.",  # optional; remove if your SDK errors on this
    ) as resp:
        for chunk in resp.iter_bytes(chunk_size=4096):
            if chunk:  # write chunks as they arrive
                stream.write(chunk)

    stream.stop_stream()
    stream.close()
    pa.terminate()


def awake_mode(buf):
    """
    Active listening: capture a full command until 3s silence.
    If 10s of total inactivity happens (i.e., we only captured silence),
    we drop back to sleep.
    """

    try:
        identity, text = transcribe_with_identify(buf)
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": pipa_core},
                {"role": "user", "content": identity + text.strip()},
            ],
        )

        text_response = response.choices[0].message.content

        say_stream(text_response)
    except Exception as e:
        logger.info(f"[awake] transcribe error: {e}")
        return

    if not text:
        logger.info("[awake] empty capture.")
        return

    logger.info(f"[awake] you said: {text}")


if __name__ == "__main__":
    try:
        while True:
            logger.info("[awake] you can speak now…")

            buf = record_until_silence(
                silence_db_threshold=-35.0, silence_seconds=2, max_record_seconds=20
            )

            if not buf:
                logger.info("entreing the sleep")
                time.sleep(2)

            if buf:
                logger.info("answering.. ")
                awake_mode(buf)

    except KeyboardInterrupt:
        logger.info("\nExiting.")
