"""Placeholder: REST API server."""
from fastapi import FastAPI

app = FastAPI(title="AI Memory OS")


@app.get("/health")
async def health():
    return {"status": "ok"}
