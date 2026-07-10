from fastapi import FastAPI

app = FastAPI(title="Stage Scheduler")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

