from datetime import date
from typing import List, Optional
from pydantic import BaseModel, EmailStr
from app.models.models import UserRole


# --- Skill Schemas ---
class SkillCreate(BaseModel):
    name: str
    is_certification: bool = False


class SkillOut(BaseModel):
    skill_id: int
    name: str
    is_certification: bool

    class Config:
        from_attributes = True


class StaffSkillAssign(BaseModel):
    skill_id: int
    expiry_date: Optional[date] = None


class StaffSkillOut(BaseModel):
    skill_id: int
    expiry_date: Optional[date] = None
    skill: SkillOut

    class Config:
        from_attributes = True


# --- Contract Schemas ---
class ContractCreate(BaseModel):
    weekly_hours: float = 45.0
    ot_allowed: bool = True


class ContractOut(BaseModel):
    contract_id: int
    staff_id: int
    weekly_hours: float
    ot_allowed: bool

    class Config:
        from_attributes = True


# --- Staff Schemas ---
class StaffCreate(BaseModel):
    site_id: int
    name: str
    email: EmailStr
    contact: Optional[str] = None
    password: str
    role: UserRole = UserRole.STAFF
    rule_groups: Optional[str] = None
    hourly_rate: float = 0.0
    contract: Optional[ContractCreate] = None


class StaffUpdate(BaseModel):
    name: Optional[str] = None
    contact: Optional[str] = None
    role: Optional[UserRole] = None
    rule_groups: Optional[str] = None
    hourly_rate: Optional[float] = None


class StaffOut(BaseModel):
    staff_id: int
    site_id: int
    name: str
    email: EmailStr
    contact: Optional[str] = None
    role: UserRole
    rule_groups: Optional[str] = None
    hourly_rate: float
    contract: Optional[ContractOut] = None
    skills: List[StaffSkillOut] = []

    class Config:
        from_attributes = True