"""FastAPI app: routes and SSE streaming."""
import logging

from fastapi import FastAPI

from app.predict import router as predict_router

# Show the workflow's step logs (app.steplog) in the server terminal.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(title="delta-t")
app.include_router(predict_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
