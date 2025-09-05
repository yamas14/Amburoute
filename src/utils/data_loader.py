def load_hospitals(csv_path: str):
    """Load hospitals from CSV file"""
    import pandas as pd
    from hospital.hospital_manager import Hospital
    
    df = pd.read_csv(csv_path)
    hospitals = []
    
    for _, row in df.iterrows():
        # For hospitals with NA beds, set a default capacity of 200
        beds = 200 if pd.isna(row['beds']) else int(row['beds'])
        
        hospital = Hospital(
            name=row['name'],
            location=(float(row['latitude']), float(row['longitude'])),
            available_beds=beds,
            has_icu=True  # Assuming all major hospitals have ICU
        )
        hospitals.append(hospital)
    
    return hospitals