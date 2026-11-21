"""Authentication route endpoints — v1."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import Agent, Customer
from ...schemas import LoginRequest, TokenOut, AgentOut, CustomerOut
from ...core.security import verify_password, create_access_token
from ...core.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenOut)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate an agent or customer with email + password. Returns a signed JWT."""
    # 1. Check Agent table
    agent = db.query(Agent).filter(
        Agent.email == payload.email,
        Agent.is_active == True,
    ).first()
    if agent and verify_password(payload.password, agent.password_hash):
        agent.last_login_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(agent)
        token = create_access_token(agent.id, agent.email, agent.role)
        return TokenOut(
            access_token=token,
            user_type="agent",
            agent=AgentOut.model_validate(agent),
        )

    # 2. Check Customer table
    customer = db.query(Customer).filter(
        Customer.email == payload.email,
        Customer.is_active == True,
    ).first()
    if customer and verify_password(payload.password, customer.password_hash):
        customer.last_login_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(customer)
        token = create_access_token(customer.id, customer.email, "customer")
        return TokenOut(
            access_token=token,
            user_type="customer",
            customer=CustomerOut.model_validate(customer),
        )

    raise HTTPException(status_code=401, detail="Invalid email or password.")


@router.get("/me")
def get_me(user_info = Depends(get_current_user)):
    """Return the currently authenticated profile (Agent or Customer)."""
    user_type, user = user_info
    if user_type == "customer":
        cust_dto = CustomerOut.model_validate(user).model_dump(mode="json")
        return {
            **cust_dto,
            "user_type": "customer",
            "customer": cust_dto,
        }
    agent_dto = AgentOut.model_validate(user).model_dump(mode="json")
    return {
        **agent_dto,
        "user_type": "agent",
        "agent": agent_dto,
    }
