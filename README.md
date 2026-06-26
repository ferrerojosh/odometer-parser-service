# Odometer Scanner (PaddleOCR)

Small FastAPI service that accepts an image and returns a best-effort odometer reading using PaddleOCR.

## 1) Install

```bash
uv sync
source .venv/bin/activate
```

## 2) Run

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

## 3) Scan an image

```bash
curl -X POST "http://127.0.0.1:8000/scan" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "image=@/absolute/path/to/odometer.jpg"
```

Example response:

```json
{
  "odometer_reading": "125734",
  "odometer_confidence": 0.9471,
  "candidates": [
    {"text": "12573", "confidence": 0.9471},
    {"text": "12573", "confidence": 0.8142}
  ]
}
```

## Notes

- First startup downloads PaddleOCR model files.
- Detection is heuristic-based and works best on sharp, front-facing odometer photos.
- If your odometer has decimals (for tenths), values like `12345.6` are supported.

## Run with Docker

Build the image:

```bash
docker build -t odometer-api .
```

Run the container:

```bash
docker run --rm -p 8000:8000 odometer-api
```

Then call the API at `http://127.0.0.1:8000`.
