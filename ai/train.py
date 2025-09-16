import os
import sys
from pathlib import Path

from stable_baselines3 import PPO

# Ensure project root is on sys.path so `backend` and `ai` are importable when running this file directly
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.hospitals import get_all_hospitals, load_hospitals_from_csv
from ai.environment import AmbulanceEnv


def train_model(ambulance_location=(12.9716, 77.5946), timesteps=20000, model_path='ai/models/hospital_router.zip'):
    # Ensure hospitals are loaded and NIMHANS is excluded by backend.hospitals
    load_hospitals_from_csv()
    hospitals = get_all_hospitals()

    if any(h['name'].strip().lower() == 'nimhans' for h in hospitals):
        raise RuntimeError('NIMHANS still present in hospitals list; expected it to be filtered out.')

    print(f"Training PPO on {len(hospitals)} hospitals (excluding NIMHANS)")

    env = AmbulanceEnv(hospitals, ambulance_location)

    # Create PPO model; simple MLP policy is sufficient
    model = PPO("MlpPolicy", env, verbose=1)
    model.learn(total_timesteps=timesteps)

    # Ensure directory exists and save the model
    Path(os.path.dirname(model_path)).mkdir(parents=True, exist_ok=True)
    model.save(model_path)
    print(f"Model saved to {model_path}")


if __name__ == "__main__":
    # Default training run
    train_model()
