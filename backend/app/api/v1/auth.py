"""Authentication route endpoints — v1."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import Agent
from ...schemas import LoginRequest, TokenOut, AgentOut
from ...core.security import verify_password, create_access_token
from ...core.dependencies import get_current_agent

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenOut)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate an agent with email + password. Returns a signed JWT."""
    agent = db.query(Agent).filter(
        Agent.email == payload.email,
        Agent.is_active == True,
    ).first()
    if not agent or not verify_password(payload.password, agent.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    agent.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(agent)
    token = create_access_token(agent.id, agent.email, agent.role)
    return TokenOut(access_token=token, agent=AgentOut.model_validate(agent))


@router.get("/me", response_model=AgentOut)
def get_me(current_agent: Agent = Depends(get_current_agent)):
    """Return the currently authenticated agent's profile."""
    return AgentOut.model_validate(current_agent)
