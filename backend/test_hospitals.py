import os
import sys
import pandas as pd

# Add the parent directory to the path so we can import the backend module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.hospitals import load_hospitals_from_csv, get_all_hospitals

def test_hospital_loading():
    print("Testing hospital data loading...")
    try:
        # Try to load the hospitals
        load_hospitals_from_csv()
        hospitals = get_all_hospitals()
        print(f"Successfully loaded {len(hospitals)} hospitals")
        if hospitals:
            print("\nFirst hospital sample:")
            print(hospitals[0])
        return True
    except Exception as e:
        print(f"Error loading hospitals: {str(e)}")
        return False

if __name__ == "__main__":
    test_hospital_loading()
