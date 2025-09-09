import gym
import numpy as np
from typing import List, Dict, Tuple, Optional, Any
from gym import spaces
import torch
import torch.nn as nn
import random
from datetime import datetime, time

from ..database.models import Hospital
from .mapbox_router import MapboxRouter, Route

class HospitalRoutingEnv(gym.Env):
    """Custom Environment for hospital routing with DRL."""
    
    metadata = {'render.modes': ['human']}
    
    def __init__(self, 
                 hospitals: List[Hospital], 
                 router: MapboxRouter,
                 max_steps: int = 100):
        super(HospitalRoutingEnv, self).__init__()
        
        self.hospitals = hospitals
        self.router = router
        self.max_steps = max_steps
        self.current_step = 0
        self.current_location = None
        self.current_time = None
        
        # Action space: select a hospital
        self.action_space = spaces.Discrete(len(hospitals))
        
        # Observation space: [current_time, current_lat, current_lon, hospital_data...]
        self.observation_space = self._get_observation_space()
        
    def _get_observation_space(self):
        """Define the observation space."""
        # Time features: hour (sin/cos), day of week (sin/cos), is_weekend
        time_features = 5
        
        # Current location features: lat, lon
        location_features = 2
        
        # Per-hospital features: lat, lon, available_beds_ratio, available_icu_ratio, 
        #                         distance_km, travel_time_mins, has_emergency, has_trauma, 
        #                         has_pediatrics, is_teaching
        hospital_features = 10
        
        # Total observation size
        obs_size = time_features + location_features + (len(self.hospitals) * hospital_features)
        
        return spaces.Box(
            low=-np.inf, 
            high=np.inf,
            shape=(obs_size,),
            dtype=np.float32
        )
    
    def reset(self):
        """Reset the environment to initial state."""
        self.current_step = 0
        self.current_time = datetime.now()
        return self._get_observation()
    
    def step(self, action: int):
        """
        Take a step in the environment.
        
        Args:
            action: Index of the selected hospital
            
        Returns:
            observation: New state
            reward: Reward for the action
            done: Whether the episode is done
            info: Additional information
        """
        if not 0 <= action < len(self.hospitals):
            raise ValueError(f"Invalid action {action}")
            
        selected_hospital = self.hospitals[action]
        
        # Get route information
        try:
            route_data = self.router.get_route(
                self.current_location,
                (selected_hospital.latitude, selected_hospital.longitude)
            )
            route = self.router.parse_route(route_data)
        except Exception as e:
            print(f"Error getting route: {e}")
            # Return a large negative reward for invalid routes
            return self._get_observation(), -1000, True, {
                'error': str(e),
                'hospital': selected_hospital,
                'route': None
            }
        
        # Calculate reward
        reward = self._calculate_reward(selected_hospital, route)
        
        # Update state
        self.current_step += 1
        done = self.current_step >= self.max_steps
        
        info = {
            'hospital': selected_hospital,
            'route': route,
            'step': self.current_step,
            'time': self.current_time
        }
        
        return self._get_observation(), reward, done, info
    
    def _get_observation(self) -> np.ndarray:
        """Convert current state to observation vector."""
        obs = []
        
        # 1. Time features
        obs.extend(self._get_time_features())
        
        # 2. Current location
        if self.current_location:
            obs.extend([self.current_location[0], self.current_location[1]])
        else:
            obs.extend([0.0, 0.0])
        
        # 3. Hospital features
        for hospital in self.hospitals:
            obs.extend(self._get_hospital_features(hospital))
        
        return np.array(obs, dtype=np.float32)
    
    def _get_time_features(self) -> List[float]:
        """Extract time-based features."""
        if not self.current_time:
            self.current_time = datetime.now()
            
        # Hour as cyclical feature (sine/cosine)
        hour = self.current_time.hour
        hour_sin = np.sin(2 * np.pi * hour / 24)
        hour_cos = np.cos(2 * np.pi * hour / 24)
        
        # Day of week (0=Monday, 6=Sunday)
        day_of_week = self.current_time.weekday()
        day_sin = np.sin(2 * np.pi * day_of_week / 7)
        day_cos = np.cos(2 * np.pi * day_of_week / 7)
        
        # Is weekend
        is_weekend = 1.0 if day_of_week >= 5 else 0.0
        
        return [hour_sin, hour_cos, day_sin, day_cos, is_weekend]
    
    def _get_hospital_features(self, hospital: Hospital) -> List[float]:
        """Extract features for a hospital."""
        if not self.current_location:
            return [0.0] * 10  # Default values if no location
            
        # Basic hospital info
        features = [
            hospital.latitude,
            hospital.longitude,
            hospital.available_beds / max(1, hospital.total_beds),  # Available bed ratio
            hospital.available_icu_beds / max(1, hospital.total_icu_beds) if hospital.total_icu_beds > 0 else 0.0,
            0.0,  # Placeholder for distance (will be updated)
            0.0,  # Placeholder for travel time (will be updated)
            1.0 if 'Emergency' in [s.specialty for s in hospital.specialties] else 0.0,
            1.0 if 'Trauma' in [s.specialty for s in hospital.specialties] else 0.0,
            1.0 if 'Pediatrics' in [s.specialty for s in hospital.specialties] else 0.0,
            1.0 if 'Teaching' in [s.name for s in hospital.specialties] else 0.0
        ]
        
        return features
    
    def _calculate_reward(self, hospital: Hospital, route: Route) -> float:
        """
        Calculate reward for selecting a hospital.
        
        Reward components:
        - Negative for travel time (shorter is better)
        - Positive for bed availability
        - Bonus for ICUs if needed
        - Penalty for choosing a hospital with no available beds
        """
        if not route:
            return -1000  # Large penalty for invalid routes
        
        # Normalize travel time (penalize longer times)
        max_expected_time = 3600  # 1 hour in seconds
        time_penalty = -min(route.duration / max_expected_time, 1.0)
        
        # Bed availability reward (higher is better)
        bed_ratio = hospital.available_beds / max(1, hospital.total_beds)
        bed_reward = 2.0 * bed_ratio  # Scale to be more significant
        
        # ICU bonus if available
        icu_bonus = 1.0 if hospital.available_icu_beds > 0 else 0.0
        
        # Penalty for no available beds
        no_beds_penalty = -10.0 if hospital.available_beds <= 0 else 0.0
        
        # Combine rewards with weights
        reward = (
            0.5 * time_penalty +
            0.3 * bed_reward +
            0.1 * icu_bonus +
            no_beds_penalty
        )
        
        return float(reward)
    
    def set_location(self, location: Tuple[float, float]):
        """Set the current location for routing."""
        self.current_location = location
    
    def set_time(self, time: datetime):
        """Set the current time for time-based features."""
        self.current_time = time


class DRLRouter:
    """DRL-based router for hospital selection."""
    
    def __init__(self, 
                 env: HospitalRoutingEnv,
                 model_path: Optional[str] = None):
        self.env = env
        self.model = None
        self.model_path = model_path
        
    def train(self, 
              total_timesteps: int = 100000,
              learning_rate: float = 0.0003,
              batch_size: int = 64,
              gamma: float = 0.99,
              tensorboard_log: Optional[str] = None):
        """Train the DRL model."""
        from stable_baselines3 import PPO
        from stable_baselines3.common.vec_env import DummyVecEnv
        from stable_baselines3.common.callbacks import EvalCallback, StopTrainingOnRewardThreshold
        
        # Create vectorized environment
        env = DummyVecEnv([lambda: self.env])
        
        # Define policy network architecture
        policy_kwargs = dict(
            activation_fn=torch.nn.ReLU,
            net_arch=[dict(pi=[128, 128], vf=[128, 128])]
        )
        
        # Initialize PPO agent
        self.model = PPO(
            "MlpPolicy",
            env,
            learning_rate=learning_rate,
            n_steps=2048,
            batch_size=batch_size,
            n_epochs=10,
            gamma=gamma,
            gae_lambda=0.95,
            clip_range=0.2,
            clip_range_vf=None,
            ent_coef=0.0,
            vf_coef=0.5,
            max_grad_norm=0.5,
            policy_kwargs=policy_kwargs,
            tensorboard_log=tensorboard_log,
            verbose=1
        )
        
        # Callbacks for evaluation
        eval_callback = EvalCallback(
            env,
            best_model_save_path="./models/best/",
            log_path="./logs/",
            eval_freq=1000,
            deterministic=True,
            render=False
        )
        
        # Train the model
        self.model.learn(
            total_timesteps=total_timesteps,
            callback=eval_callback,
            progress_bar=True
        )
        
        # Save the trained model
        if self.model_path:
            self.save(self.model_path)
        
        return self.model
    
    def predict(self, 
                location: Tuple[float, float],
                current_time: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Predict the best hospital for the given location.
        
        Args:
            location: Tuple of (latitude, longitude)
            current_time: Current time (default: now)
            
        Returns:
            Dict containing hospital and route information
        """
        if self.model is None:
            if self.model_path and os.path.exists(self.model_path):
                self.load(self.model_path)
            else:
                raise ValueError("Model not trained. Call train() first.")
        
        # Set the current location and time
        self.env.set_location(location)
        if current_time:
            self.env.set_time(current_time)
        
        # Reset environment and get initial observation
        obs = self.env.reset()
        
        # Get action from the model
        action, _ = self.model.predict(obs, deterministic=True)
        
        # Take the action to get the result
        _, _, _, info = self.env.step(action)
        
        return {
            'hospital': info['hospital'],
            'route': info['route'],
            'action': int(action)
        }
    
    def save(self, path: str):
        """Save the trained model."""
        if self.model:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self.model.save(path)
    
    @classmethod
    def load(cls, path: str, env: HospitalRoutingEnv):
        """Load a trained model."""
        from stable_baselines3 import PPO
        
        if not os.path.exists(path):
            raise FileNotFoundError(f"Model file not found: {path}")
            
        router = cls(env, path)
        router.model = PPO.load(path, env=DummyVecEnv([lambda: env]))
        return router
