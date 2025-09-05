from src.routing.path_finder import PathFinder
from src.hospital.hospital_manager import HospitalManager, Hospital

def test_basic_setup():
    # Initialize PathFinder
    path_finder = PathFinder()
    path_finder.load_road_network("Manhattan, New York, USA")
    
    # Initialize HospitalManager
    hospital_manager = HospitalManager()
    
    # Add sample hospital
    hospital = Hospital(
        id="H1",
        name="Sample Hospital",
        location=(40.7128, -74.0060),  # NYC coordinates
        total_beds=100,
        available_beds=50,
        icu_beds=20,
        available_icu_beds=10
    )
    hospital_manager.add_hospital(hospital)

if __name__ == "__main__":
    test_basic_setup()