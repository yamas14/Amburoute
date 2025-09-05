from routing.mapmyindia_router import MapmyIndiaRouter
from hospital.hospital_manager import HospitalManager, Hospital
from typing import List, Tuple, Dict
import folium
import polyline
from config import MAPMYINDIA_CLIENT_ID, MAPMYINDIA_CLIENT_SECRET, MAPMYINDIA_REST_KEY
import random

class EmergencyRoutingSystem:
    def __init__(self):
        self.router = MapmyIndiaRouter(
            client_id=MAPMYINDIA_CLIENT_ID,
            client_secret=MAPMYINDIA_CLIENT_SECRET,
            rest_key=MAPMYINDIA_REST_KEY
        )
        self.hospital_manager = HospitalManager()
    
    def find_best_hospital(self, 
                          ambulance_location: Tuple[float, float],
                          need_icu: bool = False,
                          min_beds: int = 1) -> Tuple[Hospital, Dict]:
        """Find best hospital based on availability, travel time, and traffic conditions"""
        available_hospitals = self.hospital_manager.get_available_hospitals(
            min_beds=min_beds,
            need_icu=need_icu
        )
        
        if not available_hospitals:
            raise ValueError("No hospitals with required resources available")
            
        best_hospital = None
        best_route = None
        min_score = float('inf')
        
        for hospital in available_hospitals:
            try:
                # Get route with traffic information
                route_data = self.router.get_route(
                    ambulance_location,
                    hospital.location
                )
                
                # Extract travel time and traffic delay
                base_time = route_data['legs'][0]['duration']['value']
                traffic_delay = route_data['legs'][0].get('traffic_delay', 0)
                total_time = base_time + traffic_delay
                
                # Calculate score: 60% traffic-adjusted time, 40% bed availability
                time_score = total_time * 0.6
                bed_score = (1000 / hospital.available_beds) * 0.4
                total_score = time_score + bed_score
                
                if total_score < min_score:
                    min_score = total_score
                    best_hospital = hospital
                    best_route = route_data
            except Exception as e:
                print(f"Error calculating route to {hospital.name}: {e}")
                continue
                
        if not best_hospital:
            raise ValueError("Could not find a valid route to any hospital")
            
        return best_hospital, best_route
    
    def visualize_route(self, route: Dict, hospital: Hospital, ambulance_location: Tuple[float, float]):
        """Visualize the route with ambulance position and green corridor"""
        # Handle simulation route format
        if isinstance(route['overview_polyline']['points'], list):
            coordinates = route['overview_polyline']['points']
        else:
            coordinates = polyline.decode(route['overview_polyline']['points'])
        
        # Create map centered between ambulance and hospital
        center_lat = (ambulance_location[0] + hospital.location[0]) / 2
        center_lng = (ambulance_location[1] + hospital.location[1]) / 2
        m = folium.Map(location=(center_lat, center_lng), zoom_start=12)
        
        # Add all hospitals to the map (removed min_beds filter)
        for h in self.hospital_manager.hospitals:  # Access all hospitals directly
            color = 'red' if h == hospital else 'orange'
            folium.Marker(
                h.location,
                popup=f"""
                Hospital: {h.name}
                Available Beds: {h.available_beds}
                ICU Available: {'Yes' if h.has_icu else 'No'}
                Selected: {'Yes' if h == hospital else 'No'}
                """,
                icon=folium.Icon(color=color, icon='info-sign')
            ).add_to(m)

        # Add ambulance marker
        folium.Marker(
            ambulance_location,
            popup="Ambulance Current Position",
            icon=folium.Icon(color='green', icon='ambulance', prefix='fa')
        ).add_to(m)
        
        # Add hospital marker
        folium.Marker(
            hospital.location,
            popup=f"Hospital: {hospital.name}\nAvailable Beds: {hospital.available_beds}",
            icon=folium.Icon(color='red', icon='info-sign')
        ).add_to(m)
        
        # Add intersections (replacing traffic signals)
        if 'steps' in route['legs'][0]:
            for step in route['legs'][0]['steps']:
                if 'intersections' in step:
                    for intersection in step['intersections']:
                        folium.CircleMarker(
                            location=(intersection['location'][1], intersection['location'][0]),
                            radius=5,
                            color='yellow',
                            fill=True,
                            popup=f"Intersection - {step.get('distance', 0)}m"
                        ).add_to(m)
        
        # Add route with green corridor
        folium.PolyLine(
            coordinates,
            weight=4,
            color='green',
            opacity=0.8
        ).add_to(m)
        
        return m

if __name__ == "__main__":
    # Initialize system
    system = EmergencyRoutingSystem()
    
    # Load hospitals from CSV
    from utils.data_loader import load_hospitals
    hospitals = load_hospitals('bengaluru_hospitals.csv')
    
    # Add hospitals to the system and print count
    for hospital in hospitals:
        system.hospital_manager.add_hospital(hospital)
    
    print(f"Total hospitals loaded: {len(system.hospital_manager.hospitals)}")
    for h in system.hospital_manager.hospitals:
        print(f"Hospital: {h.name}, Beds: {h.available_beds}, Location: {h.location}")
    
    # Generate random ambulance location within Bangalore boundaries
    # Bangalore approximate boundaries
    BANGALORE_BOUNDS = {
        'min_lat': 12.8,
        'max_lat': 13.05,
        'min_lng': 77.45,
        'max_lng': 77.75
    }
    
    ambulance_location = (
        random.uniform(BANGALORE_BOUNDS['min_lat'], BANGALORE_BOUNDS['max_lat']),
        random.uniform(BANGALORE_BOUNDS['min_lng'], BANGALORE_BOUNDS['max_lng'])
    )
    
    try:
        # Find best hospital and route
        hospital, route_data = system.find_best_hospital(
            ambulance_location,
            need_icu=True,
            min_beds=5
        )
        
        # Visualize route with ambulance position
        map_view = system.visualize_route(route_data, hospital, ambulance_location)
        map_view.save('emergency_route.html')
        
        print(f"Route found to {hospital.name}")
        print(f"Available beds: {hospital.available_beds}")
        print(f"Estimated travel time: {route_data['legs'][0]['duration']['text']}")
        print(f"Distance: {route_data['legs'][0]['distance']['text']}")
        print("Route map saved to emergency_route.html")
        
    except Exception as e:
        print(f"Error: {e}")