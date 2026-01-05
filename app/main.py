from fastapi import FastAPI
from app.api.routes import crew, stats

app = FastAPI(title="Veritas API")

app.include_router(crew.router)
app.include_router(stats.router)
