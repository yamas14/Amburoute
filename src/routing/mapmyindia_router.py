import requests
from typing import Tuple, Dict
import json
import time

class MapmyIndiaRouter:
    def __init__(self, client_id: str, client_secret: str, rest_key: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.rest_key = rest_key
        self.token = None
        self.last_route = None  # Initialize last_route
        self.last_route_check = 0
        self.route_update_interval = 30
        self._get_token()

    def get_route(self, origin: Tuple[float, float], 
                  destination: Tuple[float, float]) -> Dict:
        """Get detailed route information with traffic updates"""
        current_time = time.time()
        route_data = self._get_route_data(origin, destination)
        self.last_route_check = current_time
            
        # Find fastest route considering traffic
        routes = route_data['routes']
        fastest_route = min(routes, key=lambda x: x['duration'] + x.get('traffic_delay', 0))
        
        # Store the route for caching
        self.last_route = {
            'overview_polyline': {
                'points': fastest_route['geometry']
            },
            'legs': [{
                'duration': {
                    'text': f"{int((fastest_route['duration'] + fastest_route.get('traffic_delay', 0)) / 60)} mins",
                    'value': fastest_route['duration'] + fastest_route.get('traffic_delay', 0)
                },
                'distance': {
                    'text': f"{fastest_route['distance'] / 1000:.1f} km",
                    'value': fastest_route['distance']
                },
                'steps': fastest_route.get('legs', [{}])[0].get('steps', []),
                'traffic_delay': fastest_route.get('traffic_delay', 0)
            }]
        }
        
        return self.last_route

    def _get_token(self):
        """Get OAuth token"""
        auth_url = "https://outpost.mapmyindia.com/api/security/oauth/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        response = requests.post(auth_url, data=data)
        if response.status_code == 200:
            self.token = response.json()['access_token']
        else:
            raise Exception("Failed to get authentication token")

    def get_travel_time(self, origin: Tuple[float, float], 
                       destination: Tuple[float, float]) -> int:
        """Get estimated travel time in seconds"""
        route_data = self._get_route_data(origin, destination)
        return int(route_data['routes'][0]['duration'])

    def _get_route_data(self, origin: Tuple[float, float], 
                   destination: Tuple[float, float]) -> Dict:
        """Get raw route data from MapmyIndia API with traffic"""
        url = f"https://apis.mapmyindia.com/advancedmaps/v1/{self.rest_key}/route_adv/driving/"
        coords = f"{origin[1]},{origin[0]};{destination[1]},{destination[0]}"
        
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        params = {
            "geometries": "polyline",
            "overview": "full",
            "steps": "true",
            "alternatives": "true",  # Get alternative routes
            "rtype": "1",  # Include traffic info
            "region": "IND",
            "traffic": "true",  # Enable real-time traffic
            "eta": "true"  # Get estimated time with traffic
        }
        
        response = requests.get(f"{url}{coords}", headers=headers, params=params)
        if response.status_code != 200:
            raise Exception(f"Route calculation failed: {response.text}")
            
        return response.json()