from typing import Tuple, List, Dict
import googlemaps
from datetime import datetime

class GoogleMapsRouter:
    def __init__(self, api_key: str):
        self.gmaps = googlemaps.Client(key=api_key)
    
    def get_travel_time(self, origin: Tuple[float, float], 
                       destination: Tuple[float, float]) -> int:
        """Get estimated travel time in seconds"""
        result = self.gmaps.distance_matrix(
            origins=[origin],
            destinations=[destination],
            mode="driving",
            departure_time=datetime.now(),
            traffic_model="best_guess"
        )
        
        if result['rows'][0]['elements'][0]['status'] != 'OK':
            raise ValueError("Could not calculate route")
            
        return result['rows'][0]['elements'][0]['duration_in_traffic']['value']
    
    def get_route(self, origin: Tuple[float, float], 
                  destination: Tuple[float, float]) -> Dict:
        """Get detailed route information"""
        route = self.gmaps.directions(
            origin,
            destination,
            mode="driving",
            departure_time=datetime.now(),
            traffic_model="best_guess"
        )
        
        if not route:
            raise ValueError("No route found")
            
        return route[0]
    
    def get_route_with_signals(self, origin: Tuple[float, float], 
                             destination: Tuple[float, float]) -> Dict:
        """Get route with traffic signals information"""
        # Get detailed route with waypoints
        route = self.gmaps.directions(
            origin,
            destination,
            mode="driving",
            departure_time=datetime.now(),
            alternatives=False,
            traffic_model="best_guess"
        )
        
        if not route:
            raise ValueError("No route found")
            
        # Get traffic signal locations along the route
        signal_points = []
        for step in route[0]['legs'][0]['steps']:
            if 'traffic_light' in step.get('html_instructions', '').lower():
                signal_points.append({
                    'location': step['start_location'],
                    'distance': step['distance']['value']
                })
        
        return {
            'route': route[0],
            'signals': signal_points
        }
    
    def get_nearest_hospital(self, 
                           ambulance_location: Tuple[float, float],
                           hospital_locations: List[Tuple[float, float]]) -> Dict:
        """Use Distance Matrix API to find nearest hospital"""
        matrix = self.gmaps.distance_matrix(
            origins=[ambulance_location],
            destinations=hospital_locations,
            mode="driving",
            departure_time=datetime.now(),
            traffic_model="best_guess"
        )
        
        return matrix