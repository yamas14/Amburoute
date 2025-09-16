import pandas as pd
import os

# In-memory cache for hospital data
HOSPITALS_DF = None

def load_hospitals_from_csv():
    """Loads hospital data and engineers the features expected by the DRL model."""
    global HOSPITALS_DF
    csv_path = os.path.join('data', 'bengaluru_hospitals.csv')
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Hospital data not found at {csv_path}")
    
    HOSPITALS_DF = pd.read_csv(csv_path)
    HOSPITALS_DF['id'] = HOSPITALS_DF.index
    
    # Clean the 'beds' column by filling NA values with 0
    HOSPITALS_DF['beds'] = pd.to_numeric(HOSPITALS_DF['beds'], errors='coerce').fillna(0)
    
    # Engineer the features the model was trained on
    HOSPITALS_DF['total_beds'] = HOSPITALS_DF['beds']
    HOSPITALS_DF['available_beds'] = HOSPITALS_DF['beds']  # Start with all beds available
    HOSPITALS_DF['available_icu_beds'] = (HOSPITALS_DF['beds'] * 0.1).astype(int) # Assume 10% are ICU
    
    # Exclude NIMHANS from the dataset as per requirement
    initial_count = len(HOSPITALS_DF)
    HOSPITALS_DF = HOSPITALS_DF[HOSPITALS_DF['name'].str.strip().str.lower() != 'nimhans'].reset_index(drop=True)
    # Reassign IDs after filtering to keep them contiguous
    HOSPITALS_DF['id'] = HOSPITALS_DF.index
    removed = initial_count - len(HOSPITALS_DF)
    if removed:
        print(f"Filtered out {removed} hospital(s): NIMHANS")
    
    print(f"Loaded and processed {len(HOSPITALS_DF)} hospitals from {csv_path}")

def get_all_hospitals():
    """Returns a list of all hospitals as dictionaries."""
    if HOSPITALS_DF is None:
        load_hospitals_from_csv()
    return HOSPITALS_DF.to_dict('records')

import numpy as np

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
    """Randomly updates the bed counts for all hospitals to simulate a dynamic environment."""
    global HOSPITALS_DF
    if HOSPITALS_DF is None:
        load_hospitals_from_csv()

    for index, row in HOSPITALS_DF.iterrows():
        total_beds = row['total_beds']
        if total_beds > 0:
            # Randomly set available beds between 0 and total_beds
            available = np.random.randint(0, total_beds + 1)
            HOSPITALS_DF.loc[index, 'available_beds'] = available
            # Assume 10% of available beds can be ICU, but not more than total ICU beds
            max_icu = row['total_beds'] * 0.1
            HOSPITALS_DF.loc[index, 'available_icu_beds'] = np.random.randint(0, min(available, max_icu) + 1)
        else:
            HOSPITALS_DF.loc[index, 'available_beds'] = 0
            HOSPITALS_DF.loc[index, 'available_icu_beds'] = 0
    
    print("Simulated bed count updates for all hospitals.")
    return HOSPITALS_DF.to_dict('records')
