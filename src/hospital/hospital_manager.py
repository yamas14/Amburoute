from typing import List, Tuple

class Hospital:
    def __init__(self, name: str, location: Tuple[float, float], available_beds: int, has_icu: bool = True):
        self.name = name
        self.location = location
        self.available_beds = available_beds
        self.has_icu = has_icu

class HospitalManager:
    def __init__(self):
        self.hospitals = []

    def add_hospital(self, hospital: Hospital):
        self.hospitals.append(hospital)

    def get_available_hospitals(self, min_beds: int = 1, need_icu: bool = False) -> List[Hospital]:
        return [h for h in self.hospitals if h.available_beds >= min_beds and (not need_icu or h.has_icu)]