"""
API endpoints for managing hospital bed availability.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session

from src.database.models import Hospital, BedAvailabilityUpdate, BedType
from src.database.database import get_session

router = APIRouter(
    prefix="/api/beds",
    tags=["bed_management"],
    responses={404: {"description": "Not found"}},
)

# Pydantic models for request/response validation
class BedUpdateRequest(BaseModel):
    hospital_id: int
    bed_type: BedType
    new_count: int = Field(..., gt=-1, description="New count of available beds (must be non-negative)")
    updated_by: Optional[str] = None

    @validator('new_count')
    def validate_count(cls, v, values, **kwargs):
        if v < 0:
            raise ValueError('Bed count cannot be negative')
        return v

class BedHistoryFilter(BaseModel):
    hospital_id: Optional[int] = None
    bed_type: Optional[BedType] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    limit: int = 100

    @validator('end_date')
    def validate_dates(cls, v, values):
        if 'start_date' in values and v and values['start_date'] and v < values['start_date']:
            raise ValueError('end_date must be after start_date')
        return v or datetime.utcnow()

    @validator('start_date')
    def set_start_date(cls, v):
        return v or (datetime.utcnow() - timedelta(days=7))

class BedUpdateResponse(BaseModel):
    id: str
    hospital_id: int
    bed_type: str
    previous_count: int
    new_count: int
    updated_by: Optional[str]
    created_at: datetime

    class Config:
        orm_mode = True

@router.post("/update", response_model=BedUpdateResponse, status_code=status.HTTP_201_CREATED)
async def update_bed_availability(update: BedUpdateRequest, db: Session = Depends(get_session)):
    """
    Update the bed availability for a hospital.
    
    This endpoint allows updating the count of available beds (general or ICU) for a specific hospital.
    The update is recorded in the history for auditing purposes.
    """
    # Get the hospital
    hospital = db.query(Hospital).filter(Hospital.id == update.hospital_id).first()
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hospital with ID {update.hospital_id} not found"
        )
    
    try:
        # Update bed count based on bed type
        if update.bed_type == BedType.GENERAL:
            if update.new_count > hospital.total_beds:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Available beds cannot exceed total beds ({hospital.total_beds})"
                )
            previous_count = hospital.available_beds
            hospital.available_beds = update.new_count
        else:  # ICU beds
            if update.new_count > hospital.total_icu_beds:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Available ICU beds cannot exceed total ICU beds ({hospital.total_icu_beds})"
                )
            previous_count = hospital.available_icu_beds
            hospital.available_icu_beds = update.new_count
        
        # Create update record
        update_record = BedAvailabilityUpdate(
            hospital_id=hospital.id,
            bed_type=update.bed_type,
            previous_count=previous_count,
            new_count=update.new_count,
            updated_by=update.updated_by
        )
        
        db.add(update_record)
        db.commit()
        db.refresh(update_record)
        
        return update_record
        
    except ValueError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/history", response_model=List[BedUpdateResponse])
async def get_bed_update_history(
    hospital_id: Optional[int] = None,
    bed_type: Optional[BedType] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100,
    db: Session = Depends(get_session)
):
    """
    Get historical bed availability updates with filtering options.
    
    Returns a list of bed update records that match the specified criteria.
    """
    query = db.query(BedAvailabilityUpdate)
    
    # Apply filters
    if hospital_id is not None:
        query = query.filter(BedAvailabilityUpdate.hospital_id == hospital_id)
    
    if bed_type is not None:
        query = query.filter(BedAvailabilityUpdate.bed_type == bed_type)
    
    if start_date is not None:
        query = query.filter(BedAvailabilityUpdate.created_at >= start_date)
    
    if end_date is not None:
        query = query.filter(BedAvailabilityUpdate.created_at <= end_date)
    
    # Order by most recent first and apply limit
    updates = query.order_by(BedAvailabilityUpdate.created_at.desc()).limit(limit).all()
    
    return updates

@router.get("/current/{hospital_id}", response_model=dict)
async def get_current_availability(hospital_id: int, db: Session = Depends(get_session)):
    """
    Get current bed availability for a specific hospital.
    
    Returns the current counts of available and total beds (both general and ICU).
    """
    hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hospital with ID {hospital_id} not found"
        )
    
    return {
        "hospital_id": hospital.id,
        "hospital_name": hospital.name,
        "general_beds": {
            "available": hospital.available_beds,
            "total": hospital.total_beds
        },
        "icu_beds": {
            "available": hospital.available_icu_beds,
            "total": hospital.total_icu_beds
        },
        "last_updated": hospital.updated_at.isoformat() if hospital.updated_at else None
    }
