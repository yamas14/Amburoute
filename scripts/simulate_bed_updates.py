"""
Script to simulate real-time bed availability updates for testing.
"""
import os
import sys
import random
import time
import logging
from datetime import datetime, timedelta
from typing import List, Optional
import httpx
from pydantic import BaseModel

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bed_simulator.log')
    ]
)
logger = logging.getLogger(__name__)

# Configuration
class Config:
    API_BASE_URL = "http://localhost:8000"
    UPDATE_INTERVAL = 300  # 5 minutes in seconds
    HOSPITAL_IDS = [1, 2]  # Default hospital IDs to update
    
    # Bed change parameters
    MAX_BED_CHANGE = 3
    MAX_ICU_CHANGE = 2
    
    # Auto-discovery
    AUTO_DISCOVER_HOSPITALS = True  # Set to False to only update HOSPITAL_IDS
    
    # API credentials (if needed)
    API_KEY = os.getenv("AMBULANCE_API_KEY")

class BedUpdateRequest(BaseModel):
    hospital_id: int
    bed_type: str  # 'general' or 'icu'
    new_count: int
    updated_by: str = "bed_simulator"

def get_all_hospital_ids() -> List[int]:
    """Fetch all hospital IDs from the backend."""
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{Config.API_BASE_URL}/hospitals/",
                headers={"Authorization": f"Bearer {Config.API_KEY}"} if Config.API_KEY else {}
            )
            response.raise_for_status()
            hospitals = response.json()
            return [h['id'] for h in hospitals if 'id' in h]
    except Exception as e:
        logger.error(f"Error fetching hospital list: {e}")
        return []

def get_current_bed_counts(hospital_id: int) -> tuple[int, int, int, int]:
    """Get current bed counts and totals for a hospital.
    Returns: (general_available, icu_available, general_total, icu_total)
    """
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{Config.API_BASE_URL}/api/beds/current/{hospital_id}",
                headers={"Authorization": f"Bearer {Config.API_KEY}"} if Config.API_KEY else {}
            )
            response.raise_for_status()
            data = response.json()
            return (
                data["general_beds"]["available"],
                data["icu_beds"]["available"],
                data["general_beds"]["total"],
                data["icu_beds"]["total"]
            )
    except Exception as e:
        logger.error(f"Error getting current bed counts for hospital {hospital_id}: {e}")
        return 0, 0, 0, 0

def update_bed_count(hospital_id: int, bed_type: str, new_count: int) -> bool:
    """Update bed count for a hospital."""
    try:
        update = BedUpdateRequest(
            hospital_id=hospital_id,
            bed_type=bed_type,
            new_count=new_count
        )
        
        with httpx.Client() as client:
            response = client.post(
                f"{Config.API_BASE_URL}/api/beds/update",
                json=update.dict(),
                headers={"Authorization": f"Bearer {Config.API_KEY}"} if Config.API_KEY else {}
            )
            response.raise_for_status()
            logger.info(f"Updated {bed_type} beds for hospital {hospital_id} to {new_count}")
            return True
    except Exception as e:
        logger.error(f"Error updating {bed_type} beds for hospital {hospital_id}: {e}")
        return False

def simulate_bed_updates(hospital_ids: Optional[List[int]] = None):
    """Simulate bed updates for the specified hospitals."""
    if hospital_ids is None:
        if Config.AUTO_DISCOVER_HOSPITALS:
            hospital_ids = get_all_hospital_ids()
            if not hospital_ids:
                logger.warning("No hospitals found via auto-discovery, falling back to default IDs")
                hospital_ids = Config.HOSPITAL_IDS
        else:
            hospital_ids = Config.HOSPITAL_IDS
    
    logger.info(f"Starting bed simulation for hospitals: {hospital_ids}")
    logger.info(f"Update interval: {Config.UPDATE_INTERVAL} seconds")
    
    try:
        while True:
            for hospital_id in hospital_ids:
                try:
                    # Get current counts and totals
                    current_gen, current_icu, total_gen, total_icu = get_current_bed_counts(hospital_id)
                    
                    # Skip if we couldn't get current counts
                    if current_gen == 0 and current_icu == 0:
                        logger.warning(f"Skipping hospital {hospital_id} - could not get current counts")
                        continue
                    
                    # Generate random changes
                    gen_change = random.randint(-Config.MAX_BED_CHANGE, Config.MAX_BED_CHANGE)
                    icu_change = random.randint(-Config.MAX_ICU_CHANGE, Config.MAX_ICU_CHANGE)
                    
                    # Calculate new counts and clamp to [0, total]
                    new_gen = min(max(0, current_gen + gen_change), total_gen or (current_gen + max(0, Config.MAX_BED_CHANGE)))
                    new_icu = min(max(0, current_icu + icu_change), total_icu or (current_icu + max(0, Config.MAX_ICU_CHANGE)))
                    
                    # Update bed counts
                    if gen_change != 0:
                        update_bed_count(hospital_id, "general", new_gen)
                    
                    if icu_change != 0:
                        update_bed_count(hospital_id, "icu", new_icu)
                    
                except Exception as e:
                    logger.error(f"Error processing hospital {hospital_id}: {e}")
            
            # Wait for the next update interval
            time.sleep(Config.UPDATE_INTERVAL)
            
    except KeyboardInterrupt:
        logger.info("Stopping bed simulation...")
    except Exception as e:
        logger.error(f"Unexpected error in bed simulation: {e}")
        raise

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Simulate real-time bed availability updates")
    parser.add_argument(
        "--no-auto-discover", 
        action="store_false", 
        dest="auto_discover",
        help="Disable auto-discovery of hospitals and only update specified IDs"
    )
    parser.add_argument("--hospitals", type=int, nargs="+", help="Hospital IDs to simulate")
    parser.add_argument("--interval", type=int, help="Update interval in seconds")
    parser.add_argument("--max-bed-change", type=int, help="Maximum change in general beds per update")
    parser.add_argument("--max-icu-change", type=int, help="Maximum change in ICU beds per update")
    parser.add_argument("--api-url", type=str, help="Base URL of the API")
    
    args = parser.parse_args()
    
    # Update config from command line arguments
    Config.AUTO_DISCOVER_HOSPITALS = args.auto_discover
    if args.hospitals:
        Config.HOSPITAL_IDS = args.hospitals
    if args.interval:
        Config.UPDATE_INTERVAL = args.interval
    if args.max_bed_change:
        Config.MAX_BED_CHANGE = args.max_bed_change
    if args.max_icu_change:
        Config.MAX_ICU_CHANGE = args.max_icu_change
    if args.api_url:
        Config.API_BASE_URL = args.api_url.rstrip('/')
    
    # Start simulation
    simulate_bed_updates()
