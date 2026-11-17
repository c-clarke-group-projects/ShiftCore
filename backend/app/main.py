from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.staff import router as staff_router

app = FastAPI(
    title="ShiftCore API",
    description="Constraint-based shift scheduling and roster repair system",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(staff_router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "ShiftCore API"}