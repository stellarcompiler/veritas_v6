from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
import asyncio
import httpx
import uuid, json
from app.schemas.requests import CrewStartRequest
from app.schemas.responses import CrewStartResponse
from app.services.crew_runner import start_crew_process
from app.core.redis import redis_client
from app.core.redis_utils import redis_safe_mapping

router = APIRouter(prefix="/crew", tags=["crew"])

@router.post("/start", response_model=CrewStartResponse)
async def start_crew(request: Request):
    try:
        data = await request.json()
        # Handle n8n's wrapping or stringified payloads
        if isinstance(data, dict) and "body" in data:
            if isinstance(data["body"], str):
                data = json.loads(data["body"])
            elif isinstance(data["body"], dict):
                data = data["body"]
        # Validate payload using your existing schema
        req = CrewStartRequest(**data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid request format: {e}")

    job_id = str(uuid.uuid4())

    redis_client.hset(
        f"job:{job_id}:status",
        mapping=redis_safe_mapping({
            "state": "QUEUED",
            "current_agent": "PENDING"
        })
    )

    start_crew_process(req.claim, job_id)

    return {
        "job_id": job_id,
        "status": "QUEUED"
    }



@router.get("/status/{job_id}")
def poll_status(job_id: str):
    status = redis_client.hgetall(f"job:{job_id}:status")
    if not status:
        raise HTTPException(404, "Job not found")

    logs = redis_client.lrange(f"job:{job_id}:logs", 0, -1)

    return {
        "status": status,
        "logs": logs
    }

WEBHOOK_URL = "https://n8n-production-62ab.up.railway.app/webhook-test/crew-log"

@router.get("/stream/{job_id}")
async def stream_logs(job_id: str):
    last_count = 0
    while True:
        logs = redis_client.lrange(f"job:{job_id}:logs", 0, -1)
        if len(logs) > last_count:
            new_logs = logs[last_count:]
            last_count = len(logs)

            # Push logs to n8n webhook
            async with httpx.AsyncClient() as client:
                await client.post(WEBHOOK_URL, json={
                    "job_id": job_id,
                    "new_logs": new_logs
                })

        await asyncio.sleep(10)

@router.get("/result/{job_id}")
def get_result(job_id: str):
    result = redis_client.get(f"job:{job_id}:result")
    if not result:
        raise HTTPException(404, "Result not ready")

    return json.loads(result)
