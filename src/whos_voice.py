import json, numpy as np
from pathlib import Path
import torchaudio

from src.enroll_voice import wav_to_embedding


def _to_unit_vec(x, eps=1e-9):
    """Accept list/np.ndarray, return 1D float32 unit vector or None if invalid."""
    v = np.asarray(x, dtype=np.float32).reshape(-1)
    n = float(np.linalg.norm(v))
    if not np.isfinite(n) or n < eps:
        return None
    return v / (n + eps)


def who_is_speaking(
    wav_path,
    db_json="voiceprints.json",
    threshold=0.35,           # start a bit lower; calibrate later
    strategy="max",           # "max" (default) | "mean" | "avgref"
    top_k=3
):
    """
    Identify the most similar enrolled speaker or 'unknown' if below threshold.

    - threshold: cosine similarity in [-1,1] (dot product of unit vectors).
    - strategy:
        "max"    -> score(person) = max(sim over that person's templates)
        "mean"   -> score(person) = mean(sim over that person's templates)
        "avgref" -> average templates first, then sim(probe, avg_template)
    - Returns additional diagnostics: top_matches and margin.
    """

    # Load DB
    p = Path(db_json)
    if not p.exists():
        return {"speaker_id": "unknown", "confidence": 0.0, "error": f"DB '{db_json}' not found"}

    try:
        db = json.loads(p.read_text())
    except Exception as e:
        return {"speaker_id": "unknown", "confidence": 0.0, "error": f"Failed to read DB: {e}"}

    # Probe embedding
    probe = _to_unit_vec(wav_to_embedding(wav_path))
    if probe is None or not np.all(np.isfinite(probe)):
        return {"speaker_id": "unknown", "confidence": 0.0, "error": "Invalid probe embedding"}

    candidates = []

    for person, ref in db.items():
        # Normalize DB into a list of vectors
        if isinstance(ref, list) and len(ref) > 0 and isinstance(ref[0], (list, tuple, np.ndarray)):
            # multiple templates already
            vecs = [ _to_unit_vec(np.array(v, dtype=np.float32)) for v in ref ]
        else:
            # single template stored previously
            vecs = [ _to_unit_vec(np.array(ref, dtype=np.float32)) ]

        vecs = [v for v in vecs if v is not None and v.shape == probe.shape and np.all(np.isfinite(v))]
        if not vecs:
            continue

        if strategy == "avgref":
            ref_vec = _to_unit_vec(np.mean(np.stack(vecs, axis=0), axis=0))
            if ref_vec is None or ref_vec.shape != probe.shape:
                continue
            sim = float(np.dot(probe, ref_vec))
        else:
            sims = [float(np.dot(probe, v)) for v in vecs]
            sim = max(sims) if strategy == "max" else float(np.mean(sims))

        if np.isfinite(sim):
            candidates.append((person, sim))

    if not candidates:
        return {"speaker_id": "unknown", "confidence": 0.0}

    # Sort by similarity (desc)
    candidates.sort(key=lambda x: x[1], reverse=True)
    best_id, best_sim = candidates[0]
    second_sim = candidates[1][1] if len(candidates) > 1 else None
    margin = (best_sim - second_sim) if second_sim is not None else None

    return {
        "speaker_id": best_id if best_sim >= threshold else "unknown",
        "confidence": round(best_sim, 3),
        "matched_person": best_id,
        "top_matches": [(p, round(s, 3)) for p, s in candidates[:top_k]],
        "margin": round(margin, 3) if margin is not None else None,
        "strategy": strategy,
        "threshold": threshold,
    }
