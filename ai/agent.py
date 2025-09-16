import os
import numpy as np
from stable_baselines3 import PPO
from .environment import AmbulanceEnv

class DRLAgent:
    def __init__(self, model_path='ai/models/hospital_router.zip'):
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"DRL model not found at {model_path}")
        self.model = PPO.load(model_path)

    def _calculate_heuristic_score(self, hospital, ambulance_location):
        """Calculates a simple score for a hospital based on beds and distance."""
        distance = np.sqrt(
            (ambulance_location[0] - hospital['latitude'])**2 + 
            (ambulance_location[1] - hospital['longitude'])**2
        )
        bed_reward = min(hospital.get('available_beds', 0) / 10.0, 10)
        distance_penalty = distance * 50
        return bed_reward - distance_penalty

    def select_hospital(self, hospitals, ambulance_location):
        """Selects the best hospital using the DRL model trained on the full hospital set."""
        # Use all available hospitals in the DRL environment
        env = AmbulanceEnv(hospitals, ambulance_location)
        obs, _ = env.reset()
        action, _ = self.model.predict(obs, deterministic=True)
        return hospitals[action]

# Singleton instance of the agent to avoid reloading the model on every request
drl_agent = DRLAgent()
