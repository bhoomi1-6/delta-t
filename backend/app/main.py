"""FastAPI app: routes and SSE streaming."""
from fastapi import FastAPI

app = FastAPI(title="delta-t")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
