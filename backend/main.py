from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .hospitals import load_hospitals_from_csv, get_all_hospitals, update_bed_counts, simulate_bed_updates
from .routing import get_route_from_mapbox
from ai.agent import drl_agent  # Import the DRL agent
from typing import List, Dict, Tuple
from pydantic import BaseModel

# The config module is implicitly loaded by other imports, which handles .env loading.

app = FastAPI(
    title="AmbuRoute API",
    description="API for smart ambulance routing.",
    version="1.0.0"
)

# CORS middleware to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class BedUpdateRequest(BaseModel):
    available_beds: int
    available_icu_beds: int

class RouteRequest(BaseModel):
    start_coords: Tuple[float, float]
    end_coords: Tuple[float, float]

class DRLRouteRequest(BaseModel):
    ambulance_location: Tuple[float, float]

@app.on_event("startup")
def on_startup():
    """Load hospital data when the API starts."""
    load_hospitals_from_csv()

@app.get("/health", status_code=200)
def health_check():
    """Health check endpoint to confirm the API is running."""
    return {"status": "healthy"}

@app.get("/hospitals", response_model=List[Dict])
def list_hospitals():
    """Returns a list of all hospitals."""
    return get_all_hospitals()

@app.post("/hospitals/{hospital_id}/beds", status_code=200)
def update_beds(hospital_id: int, request: BedUpdateRequest):
    """Updates the bed counts for a specific hospital."""
    success = update_bed_counts(hospital_id, request.available_beds, request.available_icu_beds)
    if not success:
        raise HTTPException(status_code=404, detail="Hospital not found")
    return {"message": f"Bed counts for hospital {hospital_id} updated successfully."}

@app.post("/hospitals/simulate-updates", response_model=List[Dict])
def run_bed_simulation():
    """Simulates bed count updates for all hospitals and returns the new data."""
    return simulate_bed_updates()

@app.post("/route", response_model=Dict)
def get_route(request: RouteRequest):
    """Calculates a route between two points using Mapbox."""
    try:
        route = get_route_from_mapbox(request.start_coords, request.end_coords)
        return route
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/route/drl", response_model=Dict)
def get_drl_route(request: DRLRouteRequest):
    """Selects the best hospital using DRL and returns the route."""
    try:
        hospitals = get_all_hospitals()
        best_hospital = drl_agent.select_hospital(hospitals, request.ambulance_location)
        
        start_coords = request.ambulance_location
        end_coords = (best_hospital['latitude'], best_hospital['longitude'])
        
        route = get_route_from_mapbox(start_coords, end_coords)
        
        return {
            "hospital": best_hospital,
            "route": route
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
