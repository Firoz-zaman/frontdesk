"""Agent route endpoints — v1."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import Agent
from ...schemas import AgentOut

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("", response_model=list[AgentOut])
def list_agents(db: Session = Depends(get_db)):
    return db.query(Agent).order_by(Agent.name).all()
