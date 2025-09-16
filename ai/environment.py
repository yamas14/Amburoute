import gymnasium as gym
from gymnasium import spaces
import numpy as np

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

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        return self._get_state(), {}

    def step(self, action):
        done = True
        reward = self._calculate_reward(action)
        return self._get_state(), reward, done, False, {}

    def _get_state(self):
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

    def _calculate_reward(self, action):
        selected_hospital = self.hospitals[action]
        distance = np.sqrt(
            (self.ambulance_location[0] - selected_hospital['latitude'])**2 + 
            (self.ambulance_location[1] - selected_hospital['longitude'])**2
        )
        bed_reward = min(selected_hospital['available_beds'] / 10.0, 10)
        distance_penalty = distance * 50
        return bed_reward - distance_penalty
