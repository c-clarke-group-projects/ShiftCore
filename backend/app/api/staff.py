import hashlib
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Contract, Site, Skill, Staff, StaffSkill
from app.schemas.staff import (
    ContractCreate,
    ContractOut,
    SkillCreate,
    SkillOut,
    StaffCreate,
    StaffOut,
    StaffSkillAssign,
    StaffSkillOut,
    StaffUpdate,
)

router = APIRouter(prefix="/api", tags=["Staff, Skills & Contracts"])


def _hash_password_placeholder(raw_password: str) -> str:
    # Dulanjana (SC-111) will swap in bcrypt/JWT auth utility once merged
    return hashlib.sha256(raw_password.encode("utf-8")).hexdigest()


# --- Skills Endpoints ---
@router.post("/skills", response_model=SkillOut, status_code=status.HTTP_201_CREATED)
def create_skill(payload: SkillCreate, db: Session = Depends(get_db)):
    existing = db.query(Skill).filter(Skill.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Skill already exists")
    skill = Skill(**payload.model_dump())
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


@router.get("/skills", response_model=List[SkillOut])
def list_skills(db: Session = Depends(get_db)):
    return db.query(Skill).all()


# --- Staff CRUD Endpoints ---
@router.post("/staff", response_model=StaffOut, status_code=status.HTTP_201_CREATED)
def create_staff(payload: StaffCreate, db: Session = Depends(get_db)):
    site = db.query(Site).filter(Site.site_id == payload.site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    if db.query(Staff).filter(Staff.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    staff = Staff(
        site_id=payload.site_id,
        name=payload.name,
        email=payload.email,
        contact=payload.contact,
        hashed_password=_hash_password_placeholder(payload.password),
        role=payload.role,
        rule_groups=payload.rule_groups,
        hourly_rate=payload.hourly_rate,
    )
    db.add(staff)
    db.flush()

    contract_data = payload.contract or ContractCreate()
    contract = Contract(
        staff_id=staff.staff_id,
        weekly_hours=contract_data.weekly_hours,
        ot_allowed=contract_data.ot_allowed,
    )
    db.add(contract)
    db.commit()
    db.refresh(staff)
    return staff


@router.get("/staff", response_model=List[StaffOut])
def list_staff(site_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(Staff)
    if site_id is not None:
        query = query.filter(Staff.site_id == site_id)
    return query.all()


@router.get("/staff/{staff_id}", response_model=StaffOut)
def get_staff(staff_id: int, db: Session = Depends(get_db)):
    staff = db.query(Staff).filter(Staff.staff_id == staff_id).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")
    return staff


@router.patch("/staff/{staff_id}", response_model=StaffOut)
def update_staff(staff_id: int, payload: StaffUpdate, db: Session = Depends(get_db)):
    staff = db.query(Staff).filter(Staff.staff_id == staff_id).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(staff, field, value)

    db.commit()
    db.refresh(staff)
    return staff


@router.delete("/staff/{staff_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_staff(staff_id: int, db: Session = Depends(get_db)):
    staff = db.query(Staff).filter(Staff.staff_id == staff_id).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")
    db.delete(staff)
    db.commit()


# --- Staff Skill Assignment ---
@router.post("/staff/{staff_id}/skills", response_model=StaffSkillOut)
def assign_skill_to_staff(
    staff_id: int, payload: StaffSkillAssign, db: Session = Depends(get_db)
):
    staff = db.query(Staff).filter(Staff.staff_id == staff_id).first()
    skill = db.query(Skill).filter(Skill.skill_id == payload.skill_id).first()
    if not staff or not skill:
        raise HTTPException(status_code=404, detail="Staff or Skill not found")

    link = (
        db.query(StaffSkill)
        .filter(StaffSkill.staff_id == staff_id, StaffSkill.skill_id == payload.skill_id)
        .first()
    )
    if link:
        link.expiry_date = payload.expiry_date
    else:
        link = StaffSkill(
            staff_id=staff_id,
            skill_id=payload.skill_id,
            expiry_date=payload.expiry_date,
        )
        db.add(link)

    db.commit()
    db.refresh(link)
    return link


# --- Staff Contract Update ---
@router.put("/staff/{staff_id}/contract", response_model=ContractOut)
def upsert_staff_contract(
    staff_id: int, payload: ContractCreate, db: Session = Depends(get_db)
):
    staff = db.query(Staff).filter(Staff.staff_id == staff_id).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")

    contract = db.query(Contract).filter(Contract.staff_id == staff_id).first()
    if contract:
        contract.weekly_hours = payload.weekly_hours
        contract.ot_allowed = payload.ot_allowed
    else:
        contract = Contract(staff_id=staff_id, **payload.model_dump())
        db.add(contract)

    db.commit()
    db.refresh(contract)
    return contract