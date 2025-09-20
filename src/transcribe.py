import io
import queue
import sys
import threading
import wave
from typing import Tuple

import numpy as np
import sounddevice as sd
from openai import OpenAI

from src.config import client, logger
from whos_voice import who_is_speaking

MODEL = "gpt-4o-mini-transcribe"



def transcribe_with_identify(wav_bytes: bytes) -> Tuple[str, str]:
    """
    Accepts raw WAV bytes, identifies the speaker, and transcribes the audio
    in parallel threads.

    Returns:
        (f"{speaker_id} said: ", transcript_text)

    Raises:
        TypeError: if wav_bytes is not bytes/bytearray
        ValueError: if the payload doesn't look like a WAV file
        Any exception raised by who_is_speaking or the transcription client
    """

    if not isinstance(wav_bytes, (bytes, bytearray)):
        raise TypeError("transcribe_with_identify expects WAV bytes")

    # Minimal RIFF/WAVE sanity check
    if len(wav_bytes) < 12 or wav_bytes[:4] != b"RIFF" or wav_bytes[8:12] != b"WAVE":
        raise ValueError("Provided data does not appear to be a valid WAV file")

    # Independent buffers for each worker to avoid pointer contention
    stt_buf = io.BytesIO(wav_bytes)
    stt_buf.name = "speech.wav"
    stt_buf.seek(0)

    spk_buf = io.BytesIO(wav_bytes)
    spk_buf.name = "speech.wav"
    spk_buf.seek(0)

    # Shared result/exception holders
    results = {"speaker": None, "text": None}
    errors = {"speaker": None, "stt": None}

    def speaker_worker():
        try:
            speaker_dict = who_is_speaking(spk_buf)
            logger.info("Speaker ID result: %s", speaker_dict)
            results["speaker"] = speaker_dict
        except Exception as e:  # propagate later
            errors["speaker"] = e

    def stt_worker():
        try:
            # Ensure buffer is at start in case client reads from current offset
            stt_buf.seek(0)
            txt = client.audio.transcriptions.create(
                model=MODEL,           # e.g., "whisper-1" or "gpt-4o-transcribe"
                file=stt_buf,          # file-like; .name is set above
                response_format="text" # Whisper-style plain string
            )
            logger.info("Transcribed: %s", txt)
            results["text"] = txt
        except Exception as e:
            errors["stt"] = e

    t_speaker = threading.Thread(target=speaker_worker, name="speaker-identify", daemon=True)
    t_stt = threading.Thread(target=stt_worker, name="speech-to-text", daemon=True)

    # Kick off both in parallel
    t_speaker.start()
    t_stt.start()

    # Wait for both to finish
    t_speaker.join()
    t_stt.join()

    # If either thread failed, raise the first encountered error
    if errors["speaker"]:
        raise errors["speaker"]
    if errors["stt"]:
        raise errors["stt"]

    # Compose result
    speaker_dict = results["speaker"] or {}
    speaker_id = speaker_dict.get("speaker_id", "Someone")
    identity_prefix = f"{speaker_id} said: "
    transcript_text = results["text"] or ""

    return identity_prefix, transcript_text
