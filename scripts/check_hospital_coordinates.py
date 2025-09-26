import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from geopy.distance import geodesic

# Load the hospital data
df = pd.read_csv('data/hospitals_clean.csv')

print("Hospital Coordinate Analysis")
print("=" * 80)
print(f"Total hospitals: {len(df)}")
print(f"Wards covered: {df['ward'].nunique()}")

# Check for duplicate coordinates
duplicates = df[df.duplicated(['latitude', 'longitude'], keep=False)]
print("\nDuplicate coordinates:")
print(duplicates[['name', 'ward', 'latitude', 'longitude']].to_string() if not duplicates.empty else "No duplicate coordinates found")

# Check for nearby hospitals (within 1km)
print("\nHospitals within 1km of each other:")
found_close = False
for i in range(len(df)):
    for j in range(i + 1, len(df)):
        coord1 = (df.iloc[i]['latitude'], df.iloc[i]['longitude'])
        coord2 = (df.iloc[j]['latitude'], df.iloc[j]['longitude'])
        dist = geodesic(coord1, coord2).meters
        if dist < 1000:  # 1km in meters
            print(f"- {df.iloc[i]['name']} (Ward {df.iloc[i]['ward']}) and {df.iloc[j]['name']} (Ward {df.iloc[j]['ward']}) - {dist:.2f} meters")
            found_close = True

if not found_close:
    print("No hospitals are within 1km of each other.")

# Basic statistics
print("\nCoordinate Statistics:")
print(f"Latitude range: {df['latitude'].min():.4f}° to {df['latitude'].max():.4f}°")
print(f"Longitude range: {df['longitude'].min():.4f}° to {df['longitude'].max():.4f}°")

# Visualize the distribution
plt.figure(figsize=(12, 10))
plt.scatter(df['longitude'], df['latitude'], alpha=0.7)
plt.title('Hospital Locations in Bengaluru')
plt.xlabel('Longitude')
plt.ylabel('Latitude')

# Add labels to some points
for i, row in df.iterrows():
    if i % 3 == 0:  # Label every 3rd hospital to avoid clutter
        plt.annotate(row['name'].split()[0], (row['longitude'], row['latitude']), 
                    textcoords="offset points", xytext=(0,10), ha='center')

plt.grid(True)
plt.tight_layout()
plt.savefig('data/hospital_locations.png')
print("\nVisualization saved as 'data/hospital_locations.png'")

print("\nAnalysis complete.")
