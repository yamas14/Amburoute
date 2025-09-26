import requests
import numpy as np
from typing import List, Tuple, Optional, Dict, Any
import time
from dataclasses import dataclass

@dataclass
class Route:
    """Container for route information."""
    distance: float  # in meters
    duration: float  # in seconds
    coordinates: List[Tuple[float, float]]  # List of (lat, lon) points
    geometry: Dict[str, Any] = None
    waypoints: List[Dict[str, Any]] = None

class RoutePlanner:
    """Handles route planning using OSRM with traffic data support."""
    
    def __init__(self, osrm_url: str = "https://router.project-osrm.org"):
        self.base_url = osrm_url.rstrip('/')
        self.last_request_time = 0
        self.request_delay = 0.1  # 100ms between requests to respect rate limits
    
    def _make_request(self, url: str) -> Optional[Dict]:
        """Make a request with rate limiting."""
        # Respect rate limiting
        time_since_last = time.time() - self.last_request_time
        if time_since_last < self.request_delay:
            time.sleep(self.request_delay - time_since_last)
        
        try:
            self.last_request_time = time.time()
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Routing request failed: {e}")
            return None
    
    def get_route(self, start: Tuple[float, float], end: Tuple[float, float]) -> Route:
        """
        Get route between two points using OSRM with traffic data.
        
        Args:
            start: (latitude, longitude) of start point
            end: (latitude, longitude) of end point
            
        Returns:
            Route object containing distance, duration, and coordinates
        """
        # Convert to OSRM format (lon,lat)
        slon, slat = start[1], start[0]
        elon, elat = end[1], end[0]
        
        # Try to get route with traffic data first
        url = (
            f"{self.base_url}/route/v1/driving/{slon},{slat};{elon},{elat}?"
            "overview=full&geometries=geojson&annotations=true&steps=true"
            "&alternatives=false&continue_straight=true"
        )
        
        data = self._make_request(url)
        
        if data and data.get('code') == 'Ok' and data.get('routes'):
            route = data['routes'][0]
            coords = [(coord[1], coord[0]) for coord in route['geometry']['coordinates']]
            
            return Route(
                distance=route['distance'],
                duration=route['duration'],
                coordinates=coords,
                geometry=route['geometry'],
                waypoints=data.get('waypoints', [])
            )
        
        # Fallback to straight-line distance if routing fails
        return self._fallback_route(start, end)
    
    def get_traffic_aware_route(self, start: Tuple[float, float], end: Tuple[float, float]) -> Route:
        """
        Get route with traffic awareness (if supported by the OSRM instance).
        This requires a traffic-aware OSRM instance.
        """
        slon, slat = start[1], start[0]
        elon, elat = end[1], end[0]
        
        url = (
            f"{self.base_url}/route/v1/driving/{slon},{slat};{elon},{elat}?"
            "overview=full&geometries=geojson&annotations=duration&"
            "continue_straight=true&steps=true&alternatives=true"
        )
        
        data = self._make_request(url)
        
        if data and data.get('code') == 'Ok' and data.get('routes'):
            # Select the fastest route (OSRM should return them sorted by duration)
            route = data['routes'][0]
            coords = [(coord[1], coord[0]) for coord in route['geometry']['coordinates']]
            
            return Route(
                distance=route['distance'],
                duration=route['duration'],
                coordinates=coords,
                geometry=route['geometry'],
                waypoints=data.get('waypoints', [])
            )
        
        return self.get_route(start, end)  # Fallback to regular routing
    
    def _fallback_route(self, start: Tuple[float, float], end: Tuple[float, float]) -> Route:
        """Fallback to straight-line distance if routing service is unavailable."""
        # Haversine distance calculation
        lat1, lon1 = np.radians(start[0]), np.radians(start[1])
        lat2, lon2 = np.radians(end[0]), np.radians(end[1])
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat/2.0)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2.0)**2
        c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
        distance = 6371000 * c  # Earth's radius in meters
        
        return Route(
            distance=distance,
            duration=distance / 13.89,  # Assuming 50 km/h average speed
            coordinates=[start, end]
        )

# Global instance for easy access
route_planner = RoutePlanner()

# Example usage:
if __name__ == "__main__":
    # Test the routing
    planner = RoutePlanner()
    
    # Example coordinates (Bowring Hospital to Victoria Hospital, Bangalore)
    bowring = (12.9765, 77.5993)
    victoria = (12.9610, 77.5730)
    
    print("Getting route with traffic data...")
    route = planner.get_traffic_aware_route(bowring, victoria)
    
    print(f"Route distance: {route.distance/1000:.2f} km")
    print(f"Estimated duration: {route.duration/60:.1f} minutes")
    print(f"Number of points: {len(route.coordinates)}")
