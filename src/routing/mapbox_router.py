import requests
from typing import Tuple, Dict, Optional
import json
import time
from dataclasses import dataclass

@dataclass
class Route:
    distance: float  # meters
    duration: float  # seconds
    geometry: dict
    steps: list[dict]
    confidence: float

class MapboxRouter:
    """Router using Mapbox Directions API with real-time traffic data."""
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://api.mapbox.com/directions/v5/mapbox/driving-traffic"
        self.matrix_url = "https://api.mapbox.com/directions-matrix/v1/mapbox/driving-traffic"
        self.session = requests.Session()
        
    def get_route(self, 
                 origin: Tuple[float, float], 
                 destination: Tuple[float, float]) -> Dict:
        """
        Get route with real-time traffic data between two points.
        
        Args:
            origin: Tuple of (latitude, longitude)
            destination: Tuple of (latitude, longitude)
            
        Returns:
            Dict containing route information
        """
        # Format: [longitude, latitude]
        coordinates = f"{origin[1]},{origin[0]};{destination[1]},{destination[0]}"
        
        params = {
            'access_token': self.access_token,
            'geometries': 'geojson',
            'overview': 'full',
            'steps': 'true',
            'annotations': 'duration,distance,congestion',
            'alternatives': 'false'
        }
        
        try:
            response = self.session.get(
                f"{self.base_url}/{coordinates}",
                params=params,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"Error getting route: {e}")
            raise

    def get_route_matrix(self, 
                        origins: list[Tuple[float, float]], 
                        destinations: list[Tuple[float, float]]) -> Dict:
        """
        Get travel time matrix between multiple origins and destinations.
        
        Args:
            origins: List of (lat, lon) tuples
            destinations: List of (lat, lon) tuples
            
        Returns:
            Dict containing duration and distance matrices
        """
        # Format coordinates as [longitude, latitude]
        coordinates = []
        for point in origins + destinations:
            coordinates.append(f"{point[1]},{point[0]}")
        
        coords_str = ";".join(coordinates)
        sources = list(range(len(origins)))
        destinations = list(range(len(origins), len(origins) + len(destinations)))
        
        params = {
            'access_token': self.access_token,
            'sources': ";".join(map(str, sources)),
            'destinations': ";".join(map(str, destinations)),
            'annotations': 'duration,distance',
        }
        
        try:
            response = self.session.get(
                f"{self.matrix_url}/{coords_str}",
                params=params,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"Error getting route matrix: {e}")
            raise
            
    def get_traffic_data(self, bbox: Tuple[float, float, float, float]) -> Dict:
        """
        Get traffic data for a bounding box.
        
        Args:
            bbox: Tuple of (min_lon, min_lat, max_lon, max_lat)
            
        Returns:
            Dict containing traffic data
        """
        bbox_str = ",".join(map(str, bbox))
        
        params = {
            'access_token': self.access_token,
            'bbox': bbox_str,
        }
        
        try:
            response = self.session.get(
                "https://api.mapbox.com/v4/mapbox.mapbox-traffic-v1/tilequery/{longitude},{latitude}.json",
                params=params,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"Error getting traffic data: {e}")
            raise
            
    def parse_route(self, route_data: Dict) -> Route:
        """Parse route data into a Route object."""
        if not route_data.get('routes'):
            raise ValueError("No routes found in response")
            
        route = route_data['routes'][0]
        return Route(
            distance=route['distance'],
            duration=route['duration'],
            geometry=route['geometry'],
            steps=route.get('legs', [{}])[0].get('steps', []),
            confidence=route.get('confidence', 0)
        )
