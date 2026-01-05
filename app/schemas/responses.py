from pydantic import BaseModel

class CrewStartResponse(BaseModel):
    job_id: str
    status: str
