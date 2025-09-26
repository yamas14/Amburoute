import os
import numpy as np
from typing import List, Optional, Tuple

import pandas as pd
from pydantic import BaseModel, validator

# In-memory cache for hospital data
HOSPITALS_DF = None

class HospitalData(BaseModel):
    """Data model for hospital information with validation."""
    name: str
    beds: int
    address: str
    ward: Optional[str] = None
    latitude: float
    longitude: float
    
    @validator('beds')
    def beds_must_be_positive(cls, v):
        if v < 0:
            raise ValueError('Number of beds must be non-negative')
        return v
    
    @validator('latitude')
    def validate_latitude(cls, v):
        if not -90 <= v <= 90:
            raise ValueError('Latitude must be between -90 and 90')
        return v
    
    @validator('longitude')
    def validate_longitude(cls, v):
        if not -180 <= v <= 180:
            raise ValueError('Longitude must be between -180 and 180')
        return v

def validate_hospital_data(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """Validate the hospital DataFrame structure and content."""
    required_columns = {'name', 'beds', 'latitude', 'longitude'}
    errors = []
    
    # Check required columns
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        errors.append(f"Missing required columns: {', '.join(missing_columns)}")
    
    # Check for missing values in required columns
    for col in required_columns:
        if col in df.columns:
            # Handle beds column specially - we'll fill NAs with 0
            if col == 'beds':
                continue
            if df[col].isnull().any():
                missing_count = df[col].isnull().sum()
                errors.append(f"Column '{col}' has {missing_count} missing values")
    
    # Check for duplicate hospital names
    duplicates = df['name'].duplicated()
    if duplicates.any():
        dup_names = df[duplicates]['name'].unique()
        errors.append(f"Duplicate hospital names found: {', '.join(dup_names[:5])}{'...' if len(dup_names) > 5 else ''}")
    
    # Check coordinate ranges
    if 'latitude' in df.columns and 'longitude' in df.columns:
        invalid_lat = ((df['latitude'] < -90) | (df['latitude'] > 90)).sum()
        invalid_lon = ((df['longitude'] < -180) | (df['longitude'] > 180)).sum()
        
        if invalid_lat > 0:
            errors.append(f"Found {invalid_lat} rows with invalid latitude values (must be between -90 and 90)")
        if invalid_lon > 0:
            errors.append(f"Found {invalid_lon} rows with invalid longitude values (must be between -180 and 180)")
    
    return len(errors) == 0, errors

def load_hospitals_from_csv() -> None:
    """Loads and validates hospital data from CSV."""
    global HOSPITALS_DF
    
    # Get the absolute path to the data directory
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    csv_path = os.path.join(base_dir, 'data', 'hospitals_clean.csv')
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Hospital data not found at {csv_path}")
    
    try:
        # Read CSV with explicit data types
        df = pd.read_csv(
            csv_path,
            dtype={
                'name': str,
                'beds': 'Int64',  # Will convert to nullable integer
                'address': str,
                'ward': str,
                'latitude': float,
                'longitude': float
            },
            na_values=['NA', 'N/A', 'na', 'n/a', '']
        )
        
        # Validate the data
        is_valid, errors = validate_hospital_data(df)
        if not is_valid:
            error_msg = "\n  - " + "\n  - ".join(errors)
            raise ValueError(f"Invalid hospital data:{error_msg}")
        
        # Clean and prepare data
        # Handle missing values in beds - replace NA with 0 and convert to int
        df['beds'] = pd.to_numeric(df['beds'], errors='coerce').fillna(0).astype(int)
        df['beds'] = df['beds'].clip(lower=0)  # Ensure no negative bed counts
        
        # Exclude NIMHANS from the dataset
        initial_count = len(df)
        df = df[df['name'].str.strip().str.lower() != 'nimhans'].copy()
        
        # Reset index and assign IDs
        df = df.reset_index(drop=True)
        df['id'] = df.index
        
        # Add derived columns
        df['total_beds'] = df['beds']
        df['available_beds'] = df['beds']  # Start with all beds available
        df['available_icu_beds'] = (df['beds'] * 0.1).astype(int).clip(lower=1)  # At least 1 ICU bed if beds > 0
        
        # Calculate hospital capacity (0-1 scale)
        max_beds = df['beds'].max() if not df.empty else 1
        df['capacity'] = (df['beds'] / max_beds).clip(0, 1)
        
        # Store the validated and processed data
        HOSPITALS_DF = df
        
        # Log summary
        removed = initial_count - len(df)
        if removed:
            print(f"ℹ️  Filtered out {removed} hospital(s): NIMHANS")
        
        print(f"✅ Successfully loaded and processed {len(df)} hospitals from {csv_path}")
        print(f"   - Total beds: {df['beds'].sum():,}")
        print(f"   - Avg. beds per hospital: {df['beds'].mean():.1f}")
        
    except Exception as e:
        raise RuntimeError(f"Failed to load hospital data: {str(e)}")

def get_all_hospitals():
    """Returns a list of all hospitals as dictionaries."""
    if HOSPITALS_DF is None:
        load_hospitals_from_csv()
    return HOSPITALS_DF.to_dict('records')


def update_bed_counts(hospital_id: int, available_beds: int, available_icu_beds: int):
    """Updates the bed counts for a specific hospital."""
    global HOSPITALS_DF
    if HOSPITALS_DF is None:
        load_hospitals_from_csv()
    
    hospital_index = HOSPITALS_DF.index[HOSPITALS_DF['id'] == hospital_id]
    
    if not hospital_index.empty:
        HOSPITALS_DF.loc[hospital_index, 'available_beds'] = available_beds
        HOSPITALS_DF.loc[hospital_index, 'available_icu_beds'] = available_icu_beds
        return True
    return False

def simulate_bed_updates():
    """
    Simulates realistic hospital bed availability based on various factors:
    - Time of day (morning, afternoon, night)
    - Day of week (weekday vs weekend)
    - Hospital size and type (larger hospitals have more variation)
    - Random events (e.g., mass casualty incidents, flu season)
    """
    global HOSPITALS_DF
    if HOSPITALS_DF is None:
        load_hospitals_from_csv()
    
    # Get current time information
    import datetime
    now = datetime.datetime.now()
    hour = now.hour
    is_weekend = now.weekday() >= 5  # 5=Saturday, 6=Sunday
    
    # Define time-based factors
    time_factor = 1.0
    if 7 <= hour < 12:  # Morning
        time_factor = 0.9  # Higher occupancy in mornings
    elif 18 <= hour < 22:  # Evening
        time_factor = 0.8  # Even higher in evenings
    
    # Weekend factor
    if is_weekend:
        time_factor *= 0.9  # Slightly lower occupancy on weekends
    
    # Random event (10% chance of special event)
    special_event = None
    if np.random.random() < 0.1:  # 10% chance of special event
        special_event = np.random.choice([
            'mass_casualty', 'flu_season', 'conference', 'staff_shortage', 'equipment_maintenance'
        ])
    
    for index, row in HOSPITALS_DF.iterrows():
        total_beds = row['total_beds']
        if total_beds <= 0:
            HOSPITALS_DF.loc[index, 'available_beds'] = 0
            HOSPITALS_DF.loc[index, 'available_icu_beds'] = 0
            continue
            
        # Base availability (50-90% of total beds)
        base_availability = 0.5 + 0.4 * np.random.random()
        
        # Adjust for hospital size (larger hospitals have more variation)
        size_factor = min(1.0, 0.5 + (total_beds / 500))  # 0.5-1.5 based on size
        
        # Apply time factor
        availability = base_availability * time_factor * size_factor
        
        # Apply special event effects if any
        if special_event == 'mass_casualty':
            # Major cities get more patients
            if row['ward'] in ['Ward 126', 'Ward 75', 'Ward 125']:
                availability *= 0.3  # 70% reduction in available beds
            else:
                availability *= 0.7  # 30% reduction for others
        elif special_event == 'flu_season':
            # All hospitals affected, but larger ones more so
            availability *= 0.6 + (0.3 * (total_beds / 1000))
        
        # Calculate available beds with some randomness
        available = int(total_beds * np.clip(availability * np.random.normal(1, 0.1), 0.1, 0.95))
        
        # Ensure we don't exceed total beds
        available = max(0, min(total_beds, available))
        
        # ICU beds (10-20% of total beds, but not more than available beds)
        icu_ratio = 0.1 + (0.1 * np.random.random())  # 10-20% of total beds
        max_icu = int(total_beds * icu_ratio)
        available_icu = np.random.randint(0, min(available, max_icu) + 1)
        
        # Update the dataframe
        HOSPITALS_DF.loc[index, 'available_beds'] = available
        HOSPITALS_DF.loc[index, 'available_icu_beds'] = available_icu
        
        # Add some variability to total beds (hospitals might temporarily increase capacity)
        if np.random.random() < 0.2:  # 20% chance to adjust total beds
            adjustment = int(total_beds * np.random.normal(0, 0.05))  # ±5%
            HOSPITALS_DF.loc[index, 'total_beds'] = max(10, total_beds + adjustment)
    
    # Log the current scenario
    status = f"Simulated bed counts - Time: {now.strftime('%A %H:%M')}"
    if special_event:
        status += f" | Event: {special_event.replace('_', ' ').title()}"
    print(status)
    
    return HOSPITALS_DF.to_dict('records')
