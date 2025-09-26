import os
import random
import numpy as np
from stable_baselines3 import PPO
from .environment import AmbulanceEnv

class DRLAgent:
    def __init__(self, model_path='ai/models/hospital_router.zip'):
        if not os.path.exists(model_path):
            print("Warning: DRL model not found, falling back to heuristic selection")
            self.model = None
        else:
            self.model = PPO.load(model_path)
        
        # Weights for different factors in hospital selection
        self.weights = {
            'distance': 0.4,
            'beds': 0.3,
            'icu_beds': 0.2,
            'capacity': 0.1,
            'random': 0.1  # Small random factor for variety
        }

    def _calculate_heuristic_score(self, hospital, ambulance_location):
        """Calculates a comprehensive score for a hospital based on multiple factors."""
        # Calculate distance (in degrees, for relative comparison)
        distance = np.sqrt(
            (ambulance_location[0] - hospital['latitude'])**2 + 
            (ambulance_location[1] - hospital['longitude'])**2
        )
        
        # Normalize factors between 0 and 1
        max_beds = max(1, hospital.get('total_beds', 1))  # Avoid division by zero
        bed_utilization = hospital.get('available_beds', 0) / max_beds
        
        # Consider ICU beds if available
        icu_utilization = 0
        if 'available_icu_beds' in hospital and 'total_icu_beds' in hospital:
            max_icu = max(1, hospital['total_icu_beds'])
            icu_utilization = hospital['available_icu_beds'] / max_icu
        
        # Calculate score components
        distance_score = 1.0 / (1.0 + distance)  # Higher is better (closer)
        bed_score = min(bed_utilization * 2.0, 1.0)  # Cap at 1.0
        icu_score = min(icu_utilization * 2.0, 1.0)  # Cap at 1.0
        
        # Calculate final score with weights
        score = (
            self.weights['distance'] * distance_score +
            self.weights['beds'] * bed_score +
            self.weights['icu_beds'] * icu_score +
            self.weights['random'] * random.random()
        )
        
        return score

    def _select_top_k_hospitals(self, hospitals, ambulance_location, k=3):
        """Selects top k hospitals based on the heuristic score."""
        scored_hospitals = []
        for hospital in hospitals:
            if hospital.get('available_beds', 0) > 0:  # Only consider hospitals with available beds
                score = self._calculate_heuristic_score(hospital, ambulance_location)
                scored_hospitals.append((score, hospital))
        
        # Sort by score in descending order
        scored_hospitals.sort(reverse=True, key=lambda x: x[0])
        
        # Return top k hospitals
        return [h for (_, h) in scored_hospitals[:k]]

    def select_hospital(self, hospitals, ambulance_location):
        """
        Selects a hospital using either the DRL model or heuristic approach.
        Adds some randomness to the selection for variety.
        """
        try:
            if self.model and random.random() > 0.3:  # 70% chance to use DRL model if available
                env = AmbulanceEnv(hospitals, ambulance_location)
                obs, _ = env.reset()
                action, _ = self.model.predict(obs, deterministic=True)
                return hospitals[action]
            else:
                # Fallback to heuristic approach with some randomness
                top_hospitals = self._select_top_k_hospitals(hospitals, ambulance_location, k=3)
                if not top_hospitals:
                    # If no hospitals with available beds, just pick the closest
                    return min(hospitals, 
                             key=lambda h: np.sqrt((h['latitude'] - ambulance_location[0])**2 + 
                                                 (h['longitude'] - ambulance_location[1])**2))
                
                # Randomly select from top 3 hospitals, weighted by their scores
                scores = [self._calculate_heuristic_score(h, ambulance_location) for h in top_hospitals]
                total = sum(scores)
                if total > 0:
                    probs = [s/total for s in scores]
                    return random.choices(top_hospitals, weights=probs, k=1)[0]
                return random.choice(top_hospitals)
                
        except Exception as e:
            print(f"Error in hospital selection: {e}")
            # Fallback to simple distance-based selection
            return min(hospitals, 
                      key=lambda h: np.sqrt((h['latitude'] - ambulance_location[0])**2 + 
                                          (h['longitude'] - ambulance_location[1])**2))

# Singleton instance of the agent to avoid reloading the model on every request
drl_agent = DRLAgent()
