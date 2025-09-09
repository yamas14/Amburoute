from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, event
from sqlalchemy.orm import relationship, validates
from datetime import datetime
import os
import uuid
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, validator, Field
from enum import Enum

# Import the Base from database module
from .database import Base

# Base is now imported from database module

class Hospital(Base):
    """Hospital model to store hospital information and bed availability."""
    __tablename__ = 'hospitals'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    address = Column(Text)
    contact_number = Column(String(20))
    
    # Bed information
    total_beds = Column(Integer, default=0)
    available_beds = Column(Integer, default=0)
    total_icu_beds = Column(Integer, default=0)
    available_icu_beds = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    specialties = relationship("HospitalSpecialty", back_populates="hospital", cascade="all, delete-orphan")
    bed_updates = relationship("BedAvailabilityUpdate", back_populates="hospital", order_by="desc(BedAvailabilityUpdate.created_at)")
    
    # Validation methods
    @validates('available_beds', 'total_beds')
    def validate_bed_counts(self, key, value):
        if value < 0:
            raise ValueError(f"{key} cannot be negative")
        if key == 'available_beds' and hasattr(self, 'total_beds') and value > self.total_beds:
            raise ValueError("Available beds cannot exceed total beds")
        return value
        
    @validates('available_icu_beds', 'total_icu_beds')
    def validate_icu_bed_counts(self, key, value):
        if value < 0:
            raise ValueError(f"{key} cannot be negative")
        if key == 'available_icu_beds' and hasattr(self, 'total_icu_beds') and value > self.total_icu_beds:
            raise ValueError("Available ICU beds cannot exceed total ICU beds")
        return value
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert hospital object to dictionary."""
        return {
            'id': self.id,
            'name': self.name,
            'location': {'lat': self.latitude, 'lng': self.longitude},
            'address': self.address,
            'contact_number': self.contact_number,
            'total_beds': self.total_beds,
            'available_beds': self.available_beds,
            'total_icu_beds': self.total_icu_beds,
            'available_icu_beds': self.available_icu_beds,
            'specialties': [s.specialty for s in self.specialties],
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def update_availability(self, 
                         available_beds: Optional[int] = None, 
                         available_icu_beds: Optional[int] = None,
                         total_beds: Optional[int] = None,
                         total_icu_beds: Optional[int] = None,
                         updated_by: Optional[str] = None) -> List['BedAvailabilityUpdate']:
        """
        Update bed availability counts and track changes.
        
        Args:
            available_beds: New count of available general beds
            available_icu_beds: New count of available ICU beds
            total_beds: New total count of general beds
            total_icu_beds: New total count of ICU beds
            updated_by: Identifier for who is making the update
            
        Returns:
            List of BedAvailabilityUpdate objects created
        """
        updates = []
        session = object_session(self)
        
        # Track changes to general beds
        if available_beds is not None and available_beds != self.available_beds:
            update = BedAvailabilityUpdate(
                hospital_id=self.id,
                bed_type='general',
                previous_count=self.available_beds,
                new_count=available_beds,
                updated_by=updated_by
            )
            self.available_beds = available_beds
            updates.append(update)
            if session:
                session.add(update)
        
        # Track changes to ICU beds
        if available_icu_beds is not None and available_icu_beds != self.available_icu_beds:
            update = BedAvailabilityUpdate(
                hospital_id=self.id,
                bed_type='icu',
                previous_count=self.available_icu_beds,
                new_count=available_icu_beds,
                updated_by=updated_by
            )
            self.available_icu_beds = available_icu_beds
            updates.append(update)
            if session:
                session.add(update)
        
        # Update total counts (no history tracking for these)
        if total_beds is not None:
            self.total_beds = total_beds
        if total_icu_beds is not None:
            self.total_icu_beds = total_icu_beds
            
        return updates

class BedType(str, Enum):
    GENERAL = 'general'
    ICU = 'icu'

class BedAvailabilityUpdate(Base):
    """Model to track historical bed availability updates."""
    __tablename__ = 'bed_availability_updates'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hospital_id = Column(Integer, ForeignKey('hospitals.id'), nullable=False)
    bed_type = Column(String(10), nullable=False)  # 'general' or 'icu'
    previous_count = Column(Integer, nullable=False)
    new_count = Column(Integer, nullable=False)
    updated_by = Column(String(100), nullable=True)  # Could be system, API key, or user ID
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    hospital = relationship("Hospital", back_populates="bed_updates")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert update to dictionary."""
        return {
            'id': self.id,
            'hospital_id': self.hospital_id,
            'bed_type': self.bed_type,
            'previous_count': self.previous_count,
            'new_count': self.new_count,
            'updated_by': self.updated_by,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class HospitalSpecialty(Base):
    """Model to store hospital specialties."""
    __tablename__ = 'hospital_specialties'
    
    id = Column(Integer, primary_key=True)
    hospital_id = Column(Integer, ForeignKey('hospitals.id'), nullable=False)
    specialty = Column(String(100), nullable=False)
    
    # Relationships
    hospital = relationship("Hospital", back_populates="specialties")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert specialty to dictionary."""
        return {
            'id': self.id,
            'hospital_id': self.hospital_id,
            'specialty': self.specialty
        }


def get_session():
    """Get a database session.
    
    This is a compatibility function that will be removed in future versions.
    Use the dependency injection in FastAPI routes instead.
    """
    from .database import get_session as _get_session
    return next(_get_session())


def create_sample_data(session):
    """Create sample hospital data for testing."""
    # Clear existing data
    session.query(BedAvailabilityUpdate).delete()
    session.query(HospitalSpecialty).delete()
    session.query(Hospital).delete()
    
    # Create sample hospitals
    hospitals = [
        Hospital(
            name="City General Hospital",
            latitude=12.9716,
            longitude=77.5946,
            address="123 Main St, Bangalore",
            contact_number="+918026123456",
            total_beds=200,
            available_beds=50,
            total_icu_beds=30,
            available_icu_beds=8
        ),
        Hospital(
            name="Metro Medical Center",
            latitude=12.9816,
            longitude=77.6046,
            address="456 Oak Ave, Bangalore",
            contact_number="+918026654321",
            total_beds=150,
            available_beds=30,
            total_icu_beds=20,
            available_icu_beds=5
        )
    ]
    
    # Add specialties
    specialties = {
        "City General Hospital": ["Emergency", "Cardiology", "Neurology"],
        "Metro Medical Center": ["Emergency", "Trauma", "Orthopedics"]
    }
    
    for hospital in hospitals:
        for specialty in specialties.get(hospital.name, []):
            hospital.specialties.append(HospitalSpecialty(specialty=specialty))
    
    session.add_all(hospitals)
    session.commit()
    
    # Create some historical bed updates
    from datetime import timedelta
    import random
    
    for hospital in hospitals:
        for days_ago in range(30, 0, -1):
            update_time = datetime.utcnow() - timedelta(days=days_ago)
            
            # Randomly adjust bed counts
            new_gen_beds = max(0, min(
                hospital.total_beds,
                hospital.available_beds + random.randint(-5, 5)
            ))
            new_icu_beds = max(0, min(
                hospital.total_icu_beds,
                hospital.available_icu_beds + random.randint(-2, 2)
            ))
            
            # Create updates
            gen_update = BedAvailabilityUpdate(
                hospital_id=hospital.id,
                bed_type='general',
                previous_count=hospital.available_beds,
                new_count=new_gen_beds,
                updated_by='system',
                created_at=update_time
            )
            
            icu_update = BedAvailabilityUpdate(
                hospital_id=hospital.id,
                bed_type='icu',
                previous_count=hospital.available_icu_beds,
                new_count=new_icu_beds,
                updated_by='system',
                created_at=update_time
            )
            
            # Update hospital
            hospital.available_beds = new_gen_beds
            hospital.available_icu_beds = new_icu_beds
            
            session.add(gen_update)
            session.add(icu_update)
    
    session.commit()


if __name__ == "__main__":
    # Initialize the database and create sample data
    engine = init_db()
    session = get_session(engine)
    
    # Uncomment to create sample data
    # create_sample_data(session)
    
    # Print all hospitals
    hospitals = session.query(Hospital).all()
    for hospital in hospitals:
        print(f"{hospital.name}: {hospital.available_beds}/{hospital.total_beds} beds available")
    
    session.close()
