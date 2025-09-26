import pandas as pd
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import time
from tqdm import tqdm
import os

# Set up geocoder with a user agent
geolocator = Nominatim(user_agent="ambulance_routing_app")
# Create a rate-limited geocoding function
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)  # 1 second delay between requests

def get_coordinates(address, hospital_name):
    """Get coordinates for a given address and hospital name."""
    try:
        # Try with full address first
        location = geocode(f"{hospital_name}, {address}, Bangalore, India")
        if not location:
            # Fallback to just the street address
            location = geocode(f"{hospital_name}, {address.split(',')[0]}, Bangalore, India")
        
        if location:
            return location.latitude, location.longitude
    except Exception as e:
        print(f"Error geocoding {hospital_name}: {str(e)}")
    return None, None

def ensure_min_distance(df, min_distance=0.0005):
    """Ensure no two hospitals are too close to each other."""
    for i in range(len(df)):
        for j in range(i + 1, len(df)):
            lat1, lon1 = df.iloc[i][['latitude', 'longitude']]
            lat2, lon2 = df.iloc[j][['latitude', 'longitude']]
            
            # Calculate distance (simplified for small distances)
            dist = ((lat1 - lat2)**2 + (lon1 - lon2)**2)**0.5
            
            if dist < min_distance:
                # Move the second hospital slightly
                df.at[j, 'latitude'] += (min_distance - dist) * 0.7
                df.at[j, 'longitude'] += (min_distance - dist) * 0.7
    return df

def main():
    # File paths
    input_file = "data/hospitals_clean.csv"
    backup_file = "data/hospitals_clean_backup.csv"
    output_file = "data/hospitals_clean.csv"
    
    # Create backup
    import shutil
    shutil.copy2(input_file, backup_file)
    
    # Load data
    df = pd.read_csv(input_file)
    
    # Check if we already have coordinates
    if 'latitude' not in df.columns or 'longitude' not in df.columns:
        df['latitude'] = None
        df['longitude'] = None
    
    # Update coordinates
    updated = 0
    for idx, row in tqdm(df.iterrows(), total=len(df)):
        if pd.isna(row['latitude']) or pd.isna(row['longitude']):
            lat, lon = get_coordinates(row['address'], row['name'])
            if lat and lon:
                df.at[idx, 'latitude'] = lat
                df.at[idx, 'longitude'] = lon
                updated += 1
            time.sleep(1)  # Be nice to the geocoding service
    
    # Ensure no overlapping coordinates
    df = ensure_min_distance(df)
    
    # Save the updated data
    df.to_csv(output_file, index=False)
    print(f"\nUpdated coordinates for {updated} hospitals.")
    print(f"Original data backed up to: {backup_file}")
    print(f"Updated data saved to: {output_file}")

if __name__ == "__main__":
    main()
