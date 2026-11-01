from fastapi import FastAPI

from backend.app.api.availability import router as availability_router
from backend.app.api.blocking import router as blocking_router
from backend.app.api.calendar import router as calendar_router
from backend.app.api.schedule_validation import router as schedule_validation_router
from backend.app.api.script_analysis import router as script_analysis_router

app = FastAPI(title="Stage Scheduler")
app.include_router(availability_router)
app.include_router(blocking_router)
app.include_router(calendar_router)
app.include_router(schedule_validation_router)
app.include_router(script_analysis_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
