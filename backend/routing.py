import os
import requests
from typing import Tuple, Dict, Any
from . import config  # Ensures .env is loaded

MAPBOX_ACCESS_TOKEN = os.getenv("MAPBOX_ACCESS_TOKEN")
if not MAPBOX_ACCESS_TOKEN:
    raise ValueError("MAPBOX_ACCESS_TOKEN environment variable not set. Please ensure it is in your .env file.")

MAPBOX_DIRECTIONS_API_URL = "https://api.mapbox.com/directions/v5/mapbox/driving-traffic"

def get_route_from_mapbox(start_coords: Tuple[float, float], end_coords: Tuple[float, float]) -> Dict[str, Any]:
    """Fetches the optimal route from Mapbox Directions API with real-time traffic."""
    # Format coordinates for Mapbox API (longitude, latitude)
    coords_str = f"{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}"
    
    params = {
        'geometries': 'geojson',
        'access_token': MAPBOX_ACCESS_TOKEN
    }
    
    response = requests.get(f"{MAPBOX_DIRECTIONS_API_URL}/{coords_str}", params=params)
    response.raise_for_status()  # Raise an exception for bad status codes
    
    data = response.json()
    if not data.get('routes'):
        raise ValueError("No route found by Mapbox API.")
        
    # We only need the first, most optimal route
    return data['routes'][0]
