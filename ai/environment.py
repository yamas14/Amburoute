from typing import Tuple, Dict, Any, Optional, List
import gymnasium as gym
from gymnasium import spaces
import numpy as np
import random
from .routing import route_planner

class AmbulanceEnv(gym.Env):
    def __init__(self, hospitals, ambulance_location):
        super(AmbulanceEnv, self).__init__()
        
        self.hospitals = hospitals
        self.ambulance_location = ambulance_location
        self.num_hospitals = len(hospitals)

        # The DRL model expects a fixed size of 17 hospitals for its observation space.
        # The agent is responsible for passing exactly 17 hospitals to this environment.

        # Action space: choose one of the 17 hospitals
        self.action_space = spaces.Discrete(self.num_hospitals)

        # Observation space: 2 for ambulance + num_hospitals * 5 features each
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, 
            shape=(2 + self.num_hospitals * 5,), 
            dtype=np.float32
        )

        self.time_step_seconds = 0.1  # seconds (faster updates for smoother movement)
        self.max_steps = 1000
        self.current_step = 0
        self.current_emergency = None
        self.emergency_timer = 0
        self.current_route = None
        self.current_route_idx = 0

    def reset(self, seed: Optional[int] = None, options: Optional[Dict[str, Any]] = None) -> Tuple[np.ndarray, Dict[str, Any]]:
        super().reset(seed=seed)
        self.current_step = 0
        self.current_emergency = None
        self.emergency_timer = 0
        self.current_route = None
        self.current_route_idx = 0
        return self._get_state(), {}

    def _move_along_route(
        self, 
        current_pos: Tuple[float, float], 
        route_points: List[Tuple[float, float]],
        current_route_idx: int,
        speed_kmh: float = 50.0
    ) -> Tuple[Tuple[float, float], int, bool]:
        """
        Move along the pre-calculated route.
        
        Args:
            current_pos: Current position (lat, lon)
            route_points: List of (lat, lon) points in the route
            current_route_idx: Current index in the route points
            speed_kmh: Speed in km/h
            
        Returns:
            Tuple of (new_position, new_route_index, target_reached)
        """
        if current_route_idx >= len(route_points) - 1:
            return route_points[-1], current_route_idx, True
            
        # Get current target point
        target_pos = route_points[current_route_idx + 1]
        
        # Convert speed to meters per second
        speed_m_per_s = (speed_kmh * 1000) / 3600
        distance_per_step = speed_m_per_s * self.time_step_seconds
        
        # Calculate distance to target point
        lat1, lon1 = np.radians(current_pos[0]), np.radians(current_pos[1])
        lat2, lon2 = np.radians(target_pos[0]), np.radians(target_pos[1])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
        c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
        distance = 6371000 * c  # Earth's radius in meters
        
        if distance <= 1.0:  # Within 1 meter of target point
            # Move to next point in route
            return target_pos, current_route_idx + 1, False
            
        # Calculate movement vector
        ratio = min(1.0, distance_per_step / distance)
        new_lat = current_pos[0] + (target_pos[0] - current_pos[0]) * ratio
        new_lon = current_pos[1] + (target_pos[1] - current_pos[1]) * ratio
        
        # Check if we've reached the final destination
        is_final_point = (current_route_idx == len(route_points) - 2 and 
                         distance <= distance_per_step)
        
        return (new_lat, new_lon), current_route_idx, is_final_point

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, Dict[str, Any]]:
        """
        Take a step in the environment following road routes.
        """
        if not self.current_emergency:
            return self._get_state(), 0.0, False, {}
            
        hospital = self.hospitals[action]
        hospital_loc = (hospital['latitude'], hospital['longitude'])
        
        # Initialize route if needed
        if not hasattr(self, 'current_route') or self.current_route is None:
            # Get route using traffic-aware routing
            self.current_route = route_planner.get_traffic_aware_route(
                tuple(self.ambulance_location),
                hospital_loc
            )
            self.current_route_idx = 0
            
            if len(self.current_route.coordinates) < 2:
                print("Warning: Invalid route received, falling back to direct movement")
                self.current_route = None
                return self._fallback_step(action)
                
            print("New route to " + hospital['name'] + " with " + str(len(self.current_route.coordinates)) + " points, "
                  "distance: " + str(self.current_route.distance/1000) + " km, "
                  "duration: " + str(self.current_route.duration/60) + " min")
            
            # Add traffic information if available
            if self.current_route.traffic_data:
                traffic_factor = self.current_route.traffic_data.get('traffic_factor', 1.0)
                print(f"Traffic factor: {traffic_factor:.2f}x (real-time traffic considered)")
        
        # Move along the route
        new_pos, new_idx, target_reached = self._move_along_route(
            tuple(self.ambulance_location),
            self.current_route.coordinates,
            self.current_route_idx
        )
        
        self.ambulance_location = np.array(new_pos)
        self.current_route_idx = new_idx
        
        # Calculate reward
        reward = self._calculate_reward(action)
        
        # If we've reached the hospital, complete the emergency
        if target_reached:
            print(f"Reached hospital at {hospital_loc}")
            reward = self._calculate_reward(action)
            self.current_emergency = None
            self.emergency_timer = 0
            self.current_route = None
            self.current_route_idx = 0
        else:
            # Small negative reward for each step to encourage efficiency
            reward = -0.01
        
        # Check if episode is done
        self.current_step += 1
        done = self.current_step >= self.max_steps
        
        return self._get_state(), reward, done, {}

    def _get_state(self) -> np.ndarray:
        state = [self.ambulance_location[0], self.ambulance_location[1]]
        for hospital in self.hospitals:
            state.extend([
                hospital['latitude'], 
                hospital['longitude'], 
                hospital['available_beds'],
                hospital['available_icu_beds'],
                hospital['total_beds']
            ])
        return np.array(state, dtype=np.float32)

    def _fallback_step(self, action: int) -> Tuple[np.ndarray, float, bool, Dict[str, Any]]:
        """Fallback step method when routing fails."""
        hospital = self.hospitals[action]
        hospital_loc = np.array([hospital['latitude'], hospital['longitude']])
        
        # Simple movement towards target
        direction = hospital_loc - self.ambulance_location
        distance = np.linalg.norm(direction)
        
        if distance < 0.0001:  # ~11 meters at equator
            reward = self._calculate_reward(action)
            self.current_emergency = None
            return self._get_state(), reward, False, {}
            
        # Move towards target
        step_size = 0.0001  # ~11 meters
        self.ambulance_location = self.ambulance_location + (direction / distance) * step_size
        
        return self._get_state(), -0.01, False, {}
        
    def _calculate_reward(self, action: int) -> float:
        """
        Calculate the reward based on the chosen action using road distance.
        """
        if not self.current_emergency:
            return 0.0

        hospital = self.hospitals[action]
        hospital_loc = (hospital['latitude'], hospital['longitude'])
        
        # Get route information using OSRM
        route = route_planner.get_route(self.ambulance_location, hospital_loc)
        
        if not route or not route['coordinates']:
            # Fallback to straight-line distance if routing fails
            distance = np.sqrt(
                (self.ambulance_location[0] - hospital_loc[0])**2 + 
                (self.ambulance_location[1] - hospital_loc[1])**2
            )
            reward = 1.0 / (1.0 + distance * 111000)  # Convert to km
        else:
            # Use actual road distance in km
            distance_km = route['distance'] / 1000.0
            reward = 1.0 / (1.0 + distance_km)
        
        # Add bonus for hospitals with available beds
        bed_bonus = 0.5 if hospital['available_beds'] > 0 else 0.0
        
        # Add bonus for hospitals with ICU beds if it's a critical emergency
        icu_bonus = 1.0 if (self.current_emergency.get('severity', 0) > 7 and 
                           hospital.get('available_icu_beds', 0) > 0) else 0.0
        
        # Small random factor for exploration
        random_factor = 0.1 * (random.random() - 0.5)  # ±0.05
        
        # Combine components with weights
        reward = (
            0.6 * reward +           # Base distance-based reward (60% weight)
            0.2 * bed_bonus +        # Available beds (20% weight)
            0.1 * icu_bonus +        # ICU availability (10% weight)
            0.1 * random_factor      # Random exploration (10% weight)
        )
        
        # Penalize if no beds are available
        if hospital.get('available_beds', 0) <= 0:
            reward -= 0.5  # Significant penalty for no beds
            
        return reward
