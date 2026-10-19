from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Login(StrictModel):
    email: str = Field(min_length=5, max_length=180)
    password: str = Field(min_length=1, max_length=128)

class UserInput(StrictModel):
    email: str = Field(pattern=r'^\S+@\S+\.\S+$', max_length=180)
    name: str = Field(min_length=2, max_length=120)
    role: Literal['Admin','Manager','Employee'] = 'Employee'
    password: str = Field(min_length=10, max_length=128)

class UserEdit(StrictModel):
    name: str = Field(min_length=2, max_length=120)
    role: Literal['Admin','Manager','Employee']
    active: bool

class Profile(StrictModel):
    name: str = Field(min_length=2, max_length=120)

class ChangePassword(StrictModel):
    current_password: str
    new_password: str = Field(min_length=10,max_length=128)

class RequestWorkflow(StrictModel):
    request: str = Field(min_length=3,max_length=4000)
    conversation_id: str | None = None
    idempotency_key: str = Field(min_length=10,max_length=100)

class ToolArgs(StrictModel):
    month: str | None = Field(default=None,pattern=r'^\d{4}-(0[1-9]|1[0-2])$')
    query: str | None = Field(default=None,max_length=1000)
    product_id: str | None = None
    quantity: int | None = Field(default=None,ge=0,le=100000)

class PlanStep(StrictModel):
    tool: str = Field(max_length=80)
    arguments: ToolArgs = Field(default_factory=ToolArgs)
    label: str = Field(max_length=160)

class Plan(StrictModel):
    steps: list[PlanStep] = Field(max_length=12)
    clarification: str | None = None

class Decision(StrictModel):
    decision: Literal['approved','rejected','revision']
    revision: int = Field(ge=1)
    reason: str = Field(default='',max_length=1000)
    quantity: int | None = Field(default=None,ge=0,le=100000)

class SettingsInput(StrictModel):
    token_budget: int = Field(ge=1000,le=10000000)
    request_limit: int = Field(ge=1,le=1000)
    max_steps: int = Field(ge=1,le=12)
    timeout: int = Field(ge=5,le=300)
    approval_hours: int = Field(ge=1,le=72)
    approver_roles: list[Literal['Admin','Manager']] = Field(min_length=1)

class RoleEdit(StrictModel):
    permissions: list[str]

class ToolToggle(StrictModel):
    enabled: bool
