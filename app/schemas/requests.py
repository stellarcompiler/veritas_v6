from pydantic import BaseModel, Field

class CrewStartRequest(BaseModel):
    claim: str = Field(..., min_length=20)
