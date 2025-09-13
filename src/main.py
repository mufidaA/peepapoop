from openai import OpenAI
import os
from src.spells import pipa_core
from pathlib import Path
from src.transcribe import transcribe_with_identify
import pyaudio
from src.config import client, MODEL_ID


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


def speech_to_speech():

    transcription = transcribe_with_identify(client)
    print(transcription)

    response = client.chat.completions.create(
        model=MODEL_ID,
        messages=[
            {"role": "system", "content": pipa_core},
            {"role": "user", "content": transcription},
        ],
    )

    text_response = response.choices[0].message.content

    say_stream(text_response)


speech_to_speech()
