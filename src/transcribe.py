import io, queue, sys, wave
import numpy as np
import sounddevice as sd
from openai import OpenAI
from whos_voice import who_is_speaking
from src.config import client, logger

MODEL = "gpt-4o-mini-transcribe"  # "gpt-4o-mini-transcribe"
SAMPLERATE = 16_000
CHANNELS = 1
DTYPE = "int16"
BLOCKSIZE = 8000  # 0.5s @16kHz

audio_q = queue.Queue(maxsize=40)
chunks = []

import asyncio
import time


def audio_callback(indata, frames, time, status):
    if status:
        logger.info(status, file=sys.stderr)
    try:
        audio_q.put_nowait(bytes(indata))
    except queue.Full:
        _ = audio_q.get_nowait()
        audio_q.put_nowait(bytes(indata))


def rms_db(audio_bytes):
    # int16 -> float32 to avoid overflow on square
    x = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)

    if x.size == 0:
        return -np.inf

    # dBFS: normalize to full-scale (32768 for int16)
    x /= 32768.0

    # RMS in float, safe from overflow
    rms = np.sqrt(np.mean(x * x))  # or np.sqrt(np.mean(np.square(x)))

    # Guard against exact silence
    if not np.isfinite(rms) or rms <= 0.0:
        return -np.inf

    return 20.0 * np.log10(rms)


def record_until_silence(
    silence_db_threshold: float,
    silence_seconds: float,
    max_record_seconds: float,
) -> io.BytesIO | None:
    """
    Collects audio blocks until `silence_seconds` of continuous silence below
    `silence_db_threshold` is observed, or until `max_record_seconds` if given.
    Returns an in-memory WAV (or None if nothing captured).
    """
    chunks: list[bytes] = []
    silence_start = None
    start_time = time.time()

    try:
        while True:
            audio_q.get_nowait()
    except queue.Empty:
        pass

    with sd.RawInputStream(
        samplerate=SAMPLERATE,
        blocksize=BLOCKSIZE,
        dtype=DTYPE,
        channels=CHANNELS,
        callback=audio_callback,
    ):
        while True:
            audio_bytes = audio_q.get()
            chunks.append(audio_bytes)

            db = rms_db(audio_bytes)

            if db < silence_db_threshold:
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start >= silence_seconds:
                    break
            else:
                silence_start = None

            if (
                max_record_seconds is not None
                and (time.time() - start_time) >= max_record_seconds
            ):
                break

        if not chunks or all(rms_db(c) < silence_db_threshold for c in chunks):
            logger.info("returning None")
            return None

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(np.dtype(DTYPE).itemsize)
        wf.setframerate(SAMPLERATE)
        wf.writeframes(b"".join(chunks))
    buf.seek(0)
    buf.name = "mic.wav"
    logger.info("returning buff")
    return buf


def transcribe_with_identify(buf) -> tuple:

    speaker_dict = who_is_speaking(buf)
    logger.info(speaker_dict)
    logger.info(speaker_dict)

    txt = client.audio.transcriptions.create(
        model=MODEL,
        file=buf,
        response_format="text",  # or "json"
    )
    logger.info("Transcribed %s", txt)
    logger.info("Transcribed %s", txt)
    return (
        f"{speaker_dict["speaker_id"]} said: ",
        txt,
    )  # tx is a string when response_format="text"
