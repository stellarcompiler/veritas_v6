from multiprocessing import Process
import json
import os
import traceback

from crewai import Crew, Process as CrewProcess
from veritas.agents.claim_agent import claim_agent
from veritas.agents.researcher_agent import researcher_agent
from veritas.agents.verdict_agent import verdict_agent
from veritas.tasks import (
    create_claim_analysis_task,
    create_research_task,
    create_verdict_task
)

from app.core.redis import redis_client
from app.core.redis_utils import redis_safe_mapping
from app.services.telemetry import (
    increment_claims,
    increment_jobs_completed,
    increment_jobs_failed,
    log_event
)


# ---------------------------
# PUBLIC ENTRYPOINT
# ---------------------------

def start_crew_process(claim: str, job_id: str) -> None:
    """
    Spawn a dedicated OS process for CrewAI execution.
    FastAPI must never block on this.
    """
    p = Process(
        target=run_crew_blocking,
        args=(claim, job_id)
    )
    p.start()


# ---------------------------
# ACTUAL CREW EXECUTION
# ---------------------------

def run_crew_blocking(claim: str, job_id: str) -> None:
    """
    This runs in a SEPARATE PROCESS.
    Safe for long-running, RAM-heavy CrewAI execution.
    """
    try:
        print(f"[CREW] PID={os.getpid()} starting job {job_id}")

        redis_client.hset(
            f"job:{job_id}:status",
            mapping=redis_safe_mapping({
                "state": "RUNNING",
                "current_agent": "claim_agent"
            })
        )

        task1 = create_claim_analysis_task(claim, job_id)
        task2 = create_research_task(claim, task1, job_id)
        task3 = create_verdict_task(claim, [task1, task2])

        crew = Crew(
            agents=[claim_agent, researcher_agent, verdict_agent],
            tasks=[task1, task2, task3],
            process=CrewProcess.sequential,
            memory=False,
            verbose=True
        )

        print("[CREW] About to kickoff CrewAI")
        result = crew.kickoff()
        print("[CREW] CrewAI finished")
        log_event(
                    job_id=job_id,
                    source= "VERDICT AGENT",
                    event_type= "END",
                    message="VERDICT GENERATED",
                    meta={"ORIGIN": "VERDICT AGENT"}
                )
        redis_client.set(
            f"job:{job_id}:result",
            json.dumps(result)
        )

        redis_client.hset(
            f"job:{job_id}:status",
            mapping=redis_safe_mapping({
                "state": "COMPLETED",
                "current_agent": "FINISHED"
            })
        )

        increment_claims()
        increment_jobs_completed()

    except Exception as e:
        traceback.print_exc()
        log_event(
                    job_id=job_id,
                    source= "VERDICT AGENT",
                    event_type= "FAILED",
                    message="VERDICT GENERATION FAILED",
                    meta={"ORIGIN" : "VERDICT AGENT"}
                )
        redis_client.hset(
            f"job:{job_id}:status",
            mapping=redis_safe_mapping({
                "state": "FAILED",
                "current_agent": "ERROR"
            })
        )

        redis_client.set(
            f"job:{job_id}:result",
            json.dumps({
                "error": str(e)
            })
        )

        increment_jobs_failed()
