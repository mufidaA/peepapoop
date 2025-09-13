import io, queue, sys, wave
import numpy as np
import sounddevice as sd
from openai import OpenAI
from whos_voice import who_is_speaking

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
        print(status, file=sys.stderr)
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


def take_audio_input():
    print("Recording… (stops after 3s silence below -15 dB)")
    silence_start = None
    try:
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

                if db < -5:  # silence
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start >= 3.0:
                        print("Silence detected, stopping.")
                        break
                else:
                    silence_start = None

    except KeyboardInterrupt:
        pass

    # Pack chunks into a WAV file in memory
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(np.dtype(DTYPE).itemsize)
        wf.setframerate(SAMPLERATE)
        wf.writeframes(b"".join(chunks))
    buf.seek(0)
    buf.name = "mic.wav"
    return buf


def transcribe_with_identify(client):

    buf = take_audio_input()

    speaker_dict = who_is_speaking(buf)
    print(speaker_dict)

    txt = client.audio.transcriptions.create(
        model=MODEL,
        file=buf,
        response_format="text",  # or "json"
    )

    return f"{speaker_dict["speaker_id"]} said: {txt}"  # tx is a string when response_format="text"
