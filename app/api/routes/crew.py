from fastapi import APIRouter, HTTPException
import uuid, json
from app.schemas.requests import CrewStartRequest
from app.schemas.responses import CrewStartResponse
from app.services.crew_runner import start_crew_process
from app.core.redis import redis_client
from app.core.redis_utils import redis_safe_mapping

router = APIRouter(prefix="/crew", tags=["crew"])

@router.post("/start", response_model=CrewStartResponse)
def start_crew(req: CrewStartRequest):
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


@router.get("/result/{job_id}")
def get_result(job_id: str):
    result = redis_client.get(f"job:{job_id}:result")
    if not result:
        raise HTTPException(404, "Result not ready")

    return json.loads(result)
