import pytest
from unittest.mock import Mock, patch
import os
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

from routing.mapbox_router import MapboxRouter, Route
from database.models import Hospital, HospitalSpecialty

@pytest.fixture
def mock_requests():
    with patch('requests.Session.get') as mock_get:
        yield mock_get

@pytest.fixture
def sample_hospitals():
    """Create sample hospital data for testing."""
    hospital1 = Hospital(
        id=1,
        name="City General Hospital",
        latitude=12.9716,
        longitude=77.5946,
        total_beds=100,
        available_beds=25,
        total_icu_beds=20,
        available_icu_beds=5
    )
    
    hospital2 = Hospital(
        id=2,
        name="Metro Medical Center",
        latitude=12.9816,
        longitude=77.6046,
        total_beds=200,
        available_beds=50,
        total_icu_beds=30,
        available_icu_beds=10
    )
    
    # Add specialties
    hospital1.specialties = [
        HospitalSpecialty(specialty="Emergency"),
        HospitalSpecialty(specialty="Cardiology")
    ]
    
    hospital2.specialties = [
        HospitalSpecialty(specialty="Emergency"),
        HospitalSpecialty(specialty="Trauma")
    ]
    
    return [hospital1, hospital2]

def test_mapbox_router_initialization():
    """Test MapboxRouter initialization."""
    router = MapboxRouter("test_token")
    assert router.access_token == "test_token"
    assert "mapbox" in router.base_url

@patch('requests.Session.get')
def test_get_route(mock_get):
    """Test getting a route between two points."""
    # Mock response
    mock_response = Mock()
    mock_response.json.return_value = {
        "routes": [{
            "distance": 1000,
            "duration": 600,
            "geometry": {"type": "LineString", "coordinates": []},
            "legs": [{"steps": []}],
            "confidence": 1.0
        }]
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response
    
    # Test
    router = MapboxRouter("test_token")
    route_data = router.get_route((12.9716, 77.5946), (12.9816, 77.6046))
    
    # Assertions
    assert "routes" in route_data
    assert route_data["routes"][0]["distance"] == 1000
    assert route_data["routes"][0]["duration"] == 600

@patch('requests.Session.get')
def test_parse_route(mock_get):
    """Test parsing route data."""
    # Setup
    router = MapboxRouter("test_token")
    route_data = {
        "routes": [{
            "distance": 1000,
            "duration": 600,
            "geometry": {"type": "LineString", "coordinates": []},
            "legs": [{"steps": ["step1", "step2"]}],
            "confidence": 0.9
        }]
    }
    
    # Test
    route = router.parse_route(route_data)
    
    # Assertions
    assert isinstance(route, Route)
    assert route.distance == 1000
    assert route.duration == 600
    assert len(route.steps) == 2
    assert route.confidence == 0.9

def test_hospital_routing_env_initialization(sample_hospitals):
    """Test HospitalRoutingEnv initialization."""
    router = Mock()
    env = HospitalRoutingEnv(sample_hospitals, router)
    
    # Assertions
    assert len(env.hospitals) == 2
    assert env.action_space.n == 2  # Two hospitals
    assert env.observation_space.shape[0] > 0  # Should have positive dimension

def test_drl_router_initialization(sample_hospitals):
    """Test DRLRouter initialization."""
    router = Mock()
    env = HospitalRoutingEnv(sample_hospitals, router)
    drl_router = DRLRouter(env)
    
    # Assertions
    assert drl_router.env == env
    assert drl_router.model is None

@patch('stable_baselines3.PPO')
def test_drl_router_training(mock_ppo, sample_hospitals):
    """Test DRLRouter training."""
    # Setup
    router = Mock()
    env = HospitalRoutingEnv(sample_hospitals, router)
    drl_router = DRLRouter(env)
    
    # Mock PPO model
    mock_model = Mock()
    mock_ppo.return_value = mock_model
    
    # Test
    drl_router.train(total_timesteps=1000)
    
    # Assertions
    mock_ppo.assert_called_once()
    mock_model.learn.assert_called_once()

if __name__ == "__main__":
    pytest.main(["-v", "test_router.py"])
