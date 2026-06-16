import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from paddleocr import PaddleOCR

app = FastAPI(title="Odometer OCR", version="0.1.0")

# Load once at startup to avoid reinitializing OCR for each request.
ocr = PaddleOCR(use_angle_cls=True, lang="en")

@dataclass
class Candidate:
    text: str
    score: float

@dataclass
class TextHit:
    text: str
    score: float

def _normalize_text(raw: str) -> str:
    t = raw.strip().replace(" ", "")
    t = t.replace("O", "0").replace("o", "0")
    t = t.replace("I", "1").replace("l", "1")
    return t


def _collect_text_hits(ocr_result: Iterable) -> List[TextHit]:
    hits: List[TextHit] = []

    for line in ocr_result or []:
        # PaddleOCR v3 predict output.
        if hasattr(line, "get"):
            texts = list(line.get("rec_texts") or [])
            scores = list(line.get("rec_scores") or [])
            for i, text in enumerate(texts):
                score = float(scores[i]) if i < len(scores) else 0.5
                hits.append(TextHit(text=str(text), score=score))
            continue

        # Backward-compatible parsing for v2-style ocr output.
        for item in line or []:
            if len(item) != 2:
                continue
            text, score = item[1]
            hits.append(TextHit(text=str(text), score=float(score)))

    return hits


def _extract_candidates(text_hits: List[TextHit]) -> List[Candidate]:
    candidates: List[Candidate] = []

    def _add_text_score(text: str, score: float) -> None:
        norm = _normalize_text(str(text))
        if not norm:
            return

        # Keep digit-heavy strings, optionally with one decimal point.
        if re.fullmatch(r"\d{3,8}(?:\.\d)?", norm):
            candidates.append(Candidate(text=norm, score=float(score)))
            return

        # Fallback: extract contiguous digits from mixed text.
        digit_groups = re.findall(r"\d{3,8}", norm)
        for g in digit_groups:
            candidates.append(Candidate(text=g, score=float(score) * 0.8))

    for hit in text_hits:
        _add_text_score(hit.text, hit.score)

    return candidates


def _extract_serial_number(text_hits: List[TextHit]) -> Tuple[Optional[str], float]:
    serial_candidates: List[Candidate] = []

    patterns = [
        # Handles "No. 12345", "NO12345", "N0-12345".
        r"\bN[O0]\s*[:.#-]?\s*([A-Z0-9-]{4,20})\b",
        # Handles "Serial No. 12345".
        r"\bSERIAL\s*N[O0]\s*[:.#-]?\s*([A-Z0-9-]{4,20})\b",
    ]

    for hit in text_hits:
        raw = hit.text.strip()
        if not raw:
            continue
        upper = raw.upper()

        for pat in patterns:
            m = re.search(pat, upper)
            if not m:
                continue
            serial = m.group(1).strip("- .")
            if serial:
                serial_candidates.append(Candidate(text=serial, score=hit.score))

    if not serial_candidates:
        return None, 0.0

    best = max(serial_candidates, key=lambda c: c.score)
    return best.text, round(best.score, 4)


def _choose_best(candidates: List[Candidate]) -> Optional[Candidate]:
    if not candidates:
        return None

    # Prefer likely odometer lengths first, then OCR confidence.
    def rank_key(c: Candidate) -> Tuple[int, float]:
        raw = c.text.replace(".", "")
        length_score = 2 if 5 <= len(raw) <= 7 else 1
        return (length_score, c.score)

    return max(candidates, key=rank_key)


def _whole_odometer_value(raw: str) -> Optional[str]:
    text = (raw or "").strip()
    if not text:
        return None

    # If OCR returns explicit decimal form (e.g., 1234.5), keep only integer part.
    if "." in text:
        whole = text.split(".", 1)[0]
        digits = re.sub(r"\D", "", whole)
        return digits or None

    # If OCR returns packed digits for a 6-digit meter (e.g., 123456),
    # treat the final digit as decimal tenths and drop it.
    digits = re.sub(r"\D", "", text)
    if len(digits) == 6:
        return digits[:-1]

    return digits or None


def _decode_image(image_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Unable to decode image")
    return img


def read_odometer(image_bytes: bytes) -> dict:
    img = _decode_image(image_bytes)
    result = list(ocr.predict(img))
    text_hits = _collect_text_hits(result)
    candidates = _extract_candidates(text_hits)
    serial_number, serial_confidence = _extract_serial_number(text_hits)
    best = _choose_best(candidates)

    if best is None:
        return {
            "odometer_reading": None,
            "confidence": 0.0,
            "serial_number": serial_number,
            "serial_confidence": serial_confidence,
            "candidates": [],
            "message": "No likely odometer reading detected",
        }

    whole_reading = _whole_odometer_value(best.text)

    return {
        "odometer_reading": whole_reading,
        "confidence": round(best.score, 4),
        "serial_number": serial_number,
        "serial_confidence": serial_confidence,
        "candidates": [
            {"text": c.text, "confidence": round(c.score, 4)}
            for c in sorted(candidates, key=lambda x: x.score, reverse=True)[:10]
        ],
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/scan")
async def scan_odometer(image: UploadFile = File(...)) -> dict:
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image")

    data = await image.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded image is empty")

    try:
        return read_odometer(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"OCR failed: {exc}") from exc
