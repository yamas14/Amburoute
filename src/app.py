import os
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, HttpUrl, ConfigDict
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import logging
from sqlalchemy.orm import Session
from sqlalchemy import text

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import our modules
from src.database.models import Hospital, BedAvailabilityUpdate, BedType, create_sample_data, HospitalSpecialty
from src.database.database import init_db, get_session
from .api.bed_management import router as bed_router

# Initialize FastAPI app
app = FastAPI(
    title="AmbuRoute API",
    description="API for emergency hospital routing with real-time traffic and bed management",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Include routers
app.include_router(bed_router)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables
router = None
drl_router = None

# Models
class Location(BaseModel):
    lat: float = Field(..., ge=-90, le=90, description="Latitude")
    lng: float = Field(..., ge=-180, le=180, description="Longitude")

class HospitalResponse(BaseModel):
    id: int
    name: str
    location: Location
    address: Optional[str]
    contact_number: Optional[str]
    available_beds: int
    available_icu_beds: int
    total_beds: int
    total_icu_beds: int
    specialties: List[str] = []
    distance_km: Optional[float]
    travel_time_min: Optional[float]
    
    # Pydantic v2 config
    model_config = ConfigDict(from_attributes=True)

class RouteResponse(BaseModel):
    distance: float  # meters
    duration: float  # seconds
    geometry: Dict[str, Any]
    steps: List[Dict[str, Any]]

class RoutingResponse(BaseModel):
    hospital: HospitalResponse
    route: RouteResponse
    score: float

class ErrorResponse(BaseModel):
    detail: str
    
    class Config:
        schema_extra = {
            "example": {
                "detail": "Error message describing the issue"
            }
        }

# Initialize services
@app.on_event("startup")
async def startup_event():
    """Initialize services on application startup."""
    # Initialize database
    database_url = os.getenv("DATABASE_URL", "sqlite:///./hospitals.db")
    engine = init_db(database_url)
    app.state.engine = engine
    
    # Initialize Mapbox router (lazy import so missing module won't crash app)
    mapbox_token = os.getenv("MAPBOX_ACCESS_TOKEN")
    if not mapbox_token:
        logger.warning("MAPBOX_ACCESS_TOKEN not set. Mapbox routing will not be available.")
        app.state.router = None
    else:
        try:
            from routing.mapbox_router import MapboxRouter  # type: ignore
            app.state.router = MapboxRouter(mapbox_token)
        except Exception as e:
            logger.warning(f"Failed to initialize Mapbox router: {e}")
            app.state.router = None
    
    # Initialize DRL router
    app.state.drl_router = None
    try:
        # Try to load a pre-trained DRL model if available (lazy import)
        from routing.drl_environment import HospitalRoutingEnv, DRLRouter  # type: ignore
        if os.path.exists("models/hospital_router.zip"):
            env = HospitalRoutingEnv([], app.state.router)
            app.state.drl_router = DRLRouter(env, model_path="models/hospital_router.zip")
            logger.info("Loaded pre-trained DRL model")
    except Exception as e:
        logger.error(f"Failed to load DRL model: {e}")
    
    # Create sample data in development
    if os.getenv("ENV") == "development":
        session = None
        try:
            session = next(get_session())
            create_sample_data(session)
        except Exception as e:
            logger.error(f"Failed to create sample data: {e}")
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass

# Health check endpoint
@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """
    Health check endpoint.
    
    Returns:
        dict: Status of the application and its dependencies
    """
    status = {
        "status": "healthy",
        "services": {
            "database": "ok",
            "mapbox": "ok" if hasattr(app.state, 'router') and app.state.router else "disabled",
            "drl_model": "ok" if hasattr(app.state, 'drl_router') and app.state.drl_router else "disabled"
        },
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # Check database connection
    try:
        session = next(get_session())
        session.execute(text("SELECT 1"))
        session.close()
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        status["status"] = "degraded"
        status["services"]["database"] = "error"
    
    return status

# API endpoints
@app.post("/find-hospital", 
         response_model=RoutingResponse,
         responses={
             404: {"model": ErrorResponse},
             500: {"model": ErrorResponse}
         })
async def find_hospital(
    location: Location,
    need_icu: bool = False,
    min_beds: int = 1,
    specialty: Optional[str] = None,
    current_time: Optional[datetime] = None
):
    """
    Find the best hospital based on current location and requirements.
    
    - **location**: Current location (latitude, longitude)
    - **need_icu**: Whether ICU is required
    - **min_beds**: Minimum number of available beds required
    - **specialty**: Required medical specialty (e.g., 'Cardiology', 'Trauma')
    - **current_time**: Current time (for time-based routing)
    """
    if not getattr(app.state, 'router', None):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Routing service not available. Check Mapbox token."
        )
    
    session = next(get_session())
    try:
        # Get hospitals matching criteria
        query = session.query(Hospital).filter(
            Hospital.available_beds >= min_beds
        )
        
        if need_icu:
            query = query.filter(Hospital.available_icu_beds > 0)
            
        if specialty:
            query = query.join(Hospital.specialties).filter(
                HospitalSpecialty.specialty == specialty
            )
        
        hospitals = query.all()
        
        if not hospitals:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No hospitals found matching the criteria"
            )
        
        # Use DRL if available, otherwise fall back to simple routing
        if drl_router:
            try:
                # Set current time if provided
                if current_time is None:
                    current_time = datetime.utcnow()
                
                # Get best hospital using DRL
                result = drl_router.predict(
                    (location.lat, location.lng),
                    current_time
                )
                
                hospital = result['hospital']
                route = result['route']
                
                # Calculate score (placeholder)
                score = 1.0 - (route.duration / 3600)  # Normalize to 0-1 range
                
            except Exception as e:
                logger.error(f"DRL routing failed: {e}")
                # Fall back to simple routing
                hospital, route = _simple_routing(
                    (location.lat, location.lng), 
                    hospitals
                )
                score = 0.5  # Default score for simple routing
        else:
            # Simple routing fallback
            hospital, route = _simple_routing(
                (location.lat, location.lng), 
                hospitals
            )
            score = 0.5  # Default score for simple routing
        
        # Prepare response
        return {
            "hospital": {
                "id": hospital.id,
                "name": hospital.name,
                "location": {"lat": hospital.latitude, "lng": hospital.longitude},
                "address": hospital.address,
                "contact_number": hospital.contact_number,
                "available_beds": hospital.available_beds,
                "available_icu_beds": hospital.available_icu_beds,
                "total_beds": hospital.total_beds,
                "total_icu_beds": hospital.total_icu_beds,
                "specialties": [s.specialty for s in hospital.specialties],
                "distance_km": route.distance / 1000 if route else None,
                "travel_time_min": route.duration / 60 if route else None
            },
            "route": {
                "distance": route.distance if route else 0,
                "duration": route.duration if route else 0,
                "geometry": route.geometry if route else {},
                "steps": route.steps if route else []
            },
            "score": score
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in find_hospital")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    finally:
        session.close()

def _simple_routing(
    location: Tuple[float, float],
    hospitals: List[Hospital]
) -> Tuple[Hospital, Any]:
    """Simple routing based on distance and bed availability."""
    if not getattr(app.state, 'router', None):
        raise ValueError("Router not initialized")
    
    # Sort hospitals by distance (simple Euclidean distance as approximation)
    def distance(h):
        return ((h.latitude - location[0])**2 + 
                (h.longitude - location[1])**2)**0.5
    
    # Sort by distance and bed availability
    hospitals_sorted = sorted(
        hospitals,
        key=lambda h: (
            distance(h),
            -h.available_beds / max(1, h.total_beds)
        )
    )
    
    # Get route to the best hospital
    best_hospital = hospitals_sorted[0]
    route_data = app.state.router.get_route(
        location,
        (best_hospital.latitude, best_hospital.longitude)
    )
    
    return best_hospital, app.state.router.parse_route(route_data)

# Hospital Management Endpoints

class HospitalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    address: Optional[str] = None
    contact_number: Optional[str] = None
    total_beds: int = Field(0, ge=0)
    available_beds: int = Field(0, ge=0)
    total_icu_beds: int = Field(0, ge=0)
    available_icu_beds: int = Field(0, ge=0)
    specialties: List[str] = []

class HospitalUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    address: Optional[str] = None
    contact_number: Optional[str] = None
    total_beds: Optional[int] = Field(None, ge=0)
    total_icu_beds: Optional[int] = Field(None, ge=0)
    specialties: Optional[List[str]] = None

@app.post("/hospitals/", response_model=HospitalResponse, status_code=status.HTTP_201_CREATED)
async def create_hospital(hospital: HospitalCreate, db: Session = Depends(get_session)):
    """Create a new hospital with the given information."""
    # Check if hospital with same name already exists
    existing = db.query(Hospital).filter(Hospital.name == hospital.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Hospital with name '{hospital.name}' already exists"
        )
    
    # Create hospital
    db_hospital = Hospital(
        name=hospital.name,
        latitude=hospital.latitude,
        longitude=hospital.longitude,
        address=hospital.address,
        contact_number=hospital.contact_number,
        total_beds=hospital.total_beds,
        available_beds=min(hospital.available_beds, hospital.total_beds),
        total_icu_beds=hospital.total_icu_beds,
        available_icu_beds=min(hospital.available_icu_beds, hospital.total_icu_beds)
    )
    
    # Add specialties
    for specialty in hospital.specialties:
        db_hospital.specialties.append(HospitalSpecialty(specialty=specialty))
    
    db.add(db_hospital)
    db.commit()
    db.refresh(db_hospital)
    
    return db_hospital

@app.get("/hospitals/", response_model=List[HospitalResponse])
async def list_hospitals(
    skip: int = 0, 
    limit: int = 100,
    has_available_beds: Optional[bool] = None,
    has_available_icu: Optional[bool] = None,
    specialty: Optional[str] = None,
    db: Session = Depends(get_session)
):
    """List all hospitals with optional filtering."""
    query = db.query(Hospital)
    
    if has_available_beds is not None:
        if has_available_beds:
            query = query.filter(Hospital.available_beds > 0)
        else:
            query = query.filter(Hospital.available_beds == 0)
    
    if has_available_icu is not None:
        if has_available_icu:
            query = query.filter(Hospital.available_icu_beds > 0)
        else:
            query = query.filter(Hospital.available_icu_beds == 0)
    
    if specialty:
        query = query.join(Hospital.specialties).filter(HospitalSpecialty.specialty.ilike(f"%{specialty}%"))
    
    hospitals = query.offset(skip).limit(limit).all()
    # Serialize to HospitalResponse shape with nested location
    results = []
    for h in hospitals:
        results.append({
            "id": h.id,
            "name": h.name,
            "location": {"lat": h.latitude, "lng": h.longitude},
            "address": h.address,
            "contact_number": h.contact_number,
            "available_beds": h.available_beds,
            "available_icu_beds": h.available_icu_beds,
            "total_beds": h.total_beds,
            "total_icu_beds": h.total_icu_beds,
            "specialties": [s.specialty for s in h.specialties],
            "distance_km": None,
            "travel_time_min": None,
        })
    return results

@app.get("/hospitals/{hospital_id}", response_model=HospitalResponse)
async def get_hospital(hospital_id: int, db: Session = Depends(get_session)):
    """Get details of a specific hospital."""
    hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hospital with ID {hospital_id} not found"
        )
    return {
        "id": hospital.id,
        "name": hospital.name,
        "location": {"lat": hospital.latitude, "lng": hospital.longitude},
        "address": hospital.address,
        "contact_number": hospital.contact_number,
        "available_beds": hospital.available_beds,
        "available_icu_beds": hospital.available_icu_beds,
        "total_beds": hospital.total_beds,
        "total_icu_beds": hospital.total_icu_beds,
        "specialties": [s.specialty for s in hospital.specialties],
        "distance_km": None,
        "travel_time_min": None,
    }

if __name__ == "__main__":
    # Run the FastAPI application
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
