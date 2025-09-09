import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

from app import app
from database.models import Hospital, HospitalSpecialty, get_session

# Test client
client = TestClient(app)

@pytest.fixture
def mock_db_session():
    """Mock database session."""
    with patch('app.get_session') as mock_session:
        session = MagicMock()
        mock_session.return_value = session
        yield session

def test_health_check():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

@patch('app.router')
def test_find_hospital_success(mock_router, mock_db_session):
    """Test successful hospital finding."""
    # Mock hospital data
    hospital = Hospital(
        id=1,
        name="Test Hospital",
        latitude=12.9716,
        longitude=77.5946,
        total_beds=100,
        available_beds=25,
        total_icu_beds=20,
        available_icu_beds=5,
        address="123 Test St",
        contact_number="+1234567890"
    )
    hospital.specialties = [HospitalSpecialty(specialty="Emergency")]
    
    # Mock database query
    mock_db_session.query.return_value.filter.return_value.all.return_value = [hospital]
    
    # Mock route data
    mock_route = MagicMock()
    mock_route.distance = 1000
    mock_route.duration = 600
    mock_route.geometry = {"type": "LineString", "coordinates": []}
    mock_route.steps = ["step1", "step2"]
    
    # Mock DRL router
    with patch('app.drl_router') as mock_drl_router:
        mock_drl_router.predict.return_value = {
            'hospital': hospital,
            'route': mock_route,
            'action': 0
        }
        
        # Test API call
        response = client.get(
            "/find-hospital",
            params={
                "lat": 12.9716,
                "lng": 77.5946,
                "need_icu": True,
                "min_beds": 1
            }
        )
    
    # Assertions
    assert response.status_code == 200
    data = response.json()
    assert data["hospital"]["name"] == "Test Hospital"
    assert data["route"]["distance"] == 1000
    assert data["score"] > 0

@patch('app.router')
def test_find_hospital_no_hospitals(mock_router, mock_db_session):
    """Test when no hospitals match the criteria."""
    # Mock empty hospital list
    mock_db_session.query.return_value.filter.return_value.all.return_value = []
    
    # Test API call
    response = client.get(
        "/find-hospital",
        params={"lat": 12.9716, "lng": 77.5946}
    )
    
    # Assertions
    assert response.status_code == 404
    assert "No hospitals found" in response.json()["detail"]

@patch('app.router')
def test_find_hospital_router_error(mock_router, mock_db_session):
    """Test when there's an error with the router."""
    # Mock hospital data
    hospital = Hospital(id=1, name="Test Hospital", latitude=12.9716, longitude=77.5946)
    mock_db_session.query.return_value.filter.return_value.all.return_value = [hospital]
    
    # Mock router to raise an exception
    mock_router.get_route.side_effect = Exception("Routing error")
    
    # Test API call
    response = client.get(
        "/find-hospital",
        params={"lat": 12.9716, "lng": 77.5946}
    )
    
    # Assertions
    assert response.status_code == 500
    assert "error" in response.json()["detail"]

if __name__ == "__main__":
    pytest.main(["-v", "test_api.py"])
