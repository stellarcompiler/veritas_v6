from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import crew, stats

app = FastAPI(title="Veritas API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "https://brunilda-preponderant-legend.ngrok-free.dev",
        "https://nh34qdxh-8000.inc1.devtunnels.ms",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(crew.router)
app.include_router(stats.router)
