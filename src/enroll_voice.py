import json
from pathlib import Path

import numpy as np
import torch
import torchaudio
from speechbrain.inference import EncoderClassifier

# load once
classifier = EncoderClassifier.from_hparams(
    source="speechbrain/spkrec-ecapa-voxceleb", run_opts={"device": "cpu"}
)

torch.amp.custom_fwd(device_type="cpu", cast_inputs=torch.float16)
def fwd(x):
    return x * 2

wrapped_fwd = torch.amp.custom_fwd(fwd, device_type="cpu", cast_inputs=torch.float16)

def _ensure_16k_mono(wav, sr):
    """Resample to 16kHz mono tensor (1, samples)."""
    if sr != 16000:
        resampler = torchaudio.transforms.Resample(
            orig_freq=sr,
            new_freq=16000,
            lowpass_filter_width=64,
            rolloff=0.9475937167399596,
            resampling_method="sinc_interp_kaiser",
            beta=14.769656459379492,
        )
        wav = resampler(wav)
    # mono: average channels
    if wav.dim() == 2 and wav.size(0) > 1:
        wav = wav.mean(dim=0, keepdim=True)
    elif wav.dim() == 1:
        wav = wav.unsqueeze(0)
    return wav


def _trim_long_silences(wav, sample_rate=16000, max_silence_sec=5):
    """
    Remove silence longer than max_silence_sec at beginning/end.
    Uses simple energy thresholding.
    """
    energy = wav.abs().mean(dim=0)
    threshold = 0.001  # tweakable
    active = energy > threshold
    if not active.any():
        return wav

    idx = active.nonzero().squeeze()
    start, end = idx[0].item(), idx[-1].item()

    # shrink silence windows > max_silence_sec
    max_silence = int(max_silence_sec * sample_rate)
    if start > max_silence:
        start = max_silence
    if (wav.size(1) - end) > max_silence:
        end = wav.size(1) - max_silence
    return wav[:, start:end]


def wav_to_embedding(file_or_path):
    """
    Accepts either a filesystem path OR a file-like object (BytesIO).
    """
    # Load WAV (handle BytesIO or path)
    if hasattr(file_or_path, "read"):
        file_or_path.seek(0)  # important for BytesIO
        wav, sr = torchaudio.load(file_or_path, format="wav")
    else:
        wav, sr = torchaudio.load(file_or_path)

    wav = _ensure_16k_mono(wav, sr)
    wav = _trim_long_silences(wav)

    with torch.no_grad():
        emb = classifier.encode_batch(wav)  # (1, 192) expected
    emb = emb.squeeze(0).cpu().numpy()

    # Make the embedding robust
    if not np.isfinite(emb).all():
        # replace NaNs/inf with zeros (or small eps)
        emb = np.nan_to_num(emb, nan=0.0, posinf=0.0, neginf=0.0)

    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    else:
        # fallback: return a zero vector instead of None/Falsey
        emb = np.zeros_like(emb)

    return emb


def enroll(person, wav_paths, out_json="voiceprints.json"):
    db = json.loads(Path(out_json).read_text()) if Path(out_json).exists() else {}

    # compute embeddings for each clip (unit-normalized inside wav_to_embedding)
    embs = [wav_to_embedding(p) for p in wav_paths]

    # store as a list of vectors rather than a single mean
    existing = db.get(person, [])
    if (
        isinstance(existing, list)
        and existing
        and isinstance(existing[0], (list, tuple))
    ):
        existing_vecs = existing
    elif isinstance(existing, list) and existing:
        # was a single vector before; convert to list of vectors
        existing_vecs = [existing]
    else:
        existing_vecs = []

    existing_vecs.extend(e.tolist() for e in embs)
    db[person] = existing_vecs

    Path(out_json).write_text(json.dumps(db, indent=2))
    print(
        f"Enrolled {person} with {len(wav_paths)} new clips; total templates now {len(existing_vecs)}."
    )


# enroll("Hilla", ["voice_lib/hilla1.wav", "voice_lib/hilla2.wav", "voice_lib/hilla3.wav"])
# enroll("Arto",   ["voice_lib/arto1.wav",   "voice_lib/arto2.wav",   "voice_lib/arto3.wav"])
# enroll("Mufida", ["voice_lib/mufida1.wav", "voice_lib/mufida2.wav", "voice_lib/mufida3.wav"])
