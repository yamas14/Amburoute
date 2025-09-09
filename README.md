# AmbuRoute - Emergency Hospital Routing System

AmbuRoute is an intelligent emergency response system that helps ambulances find the best hospital based on real-time traffic conditions, hospital bed availability, and other critical factors using Deep Reinforcement Learning (DRL).

## Features

- **Real-time Traffic-Aware Routing**: Uses Mapbox Directions API for accurate, traffic-aware routing
- **Hospital Bed Availability**: Considers current bed and ICU availability when selecting hospitals
- **Deep Reinforcement Learning**: Uses DRL to optimize hospital selection based on multiple factors
- **RESTful API**: Easy-to-use HTTP API for integration with other systems
- **Scalable Architecture**: Built with FastAPI and SQLAlchemy for performance and scalability

## Prerequisites

- Python 3.8+
- Mapbox Access Token (get one at [Mapbox](https://account.mapbox.com/))
- PostgreSQL (recommended) or SQLite

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/AmbuRoute.git
   cd AmbuRoute
   ```

2. Create a virtual environment and activate it:
   ```bash
   # Windows
   python -m venv venv
   .\venv\Scripts\activate
   
   # Linux/MacOS
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install the package in development mode:
   ```bash
   pip install -e .
   ```

4. Create a `.env` file in the root directory:
   ```env
   # Environment (development/production)
   ENV=development
   
   # Mapbox Access Token (required for routing)
   MAPBOX_ACCESS_TOKEN=your_mapbox_access_token_here
   
   # Database URL (defaults to SQLite)
   DATABASE_URL=sqlite:///./hospitals.db
   
   # For PostgreSQL:
   # DATABASE_URL=postgresql://user:password@localhost/amburoute
   
   # Server configuration
   HOST=0.0.0.0
   PORT=8000
   RELOAD=true
   LOG_LEVEL=info
   ```

## Database Setup

1. Initialize the database:
   ```bash
   python -c "from database.models import init_db; init_db()"
   ```

2. (Optional) Load sample hospital data:
   ```bash
   python -c "from database.models import create_sample_data, get_session; create_sample_data(get_session())"
   ```

## Running the Application

1. Initialize the database and create sample data:
   ```bash
   python -c "from src.database.models import create_sample_data; from src.database.database import get_session; create_sample_data(next(get_session()))"
   ```

2. Start the development server:
   ```bash
   # Using the package's entry point
   python -m src
   
   # Or directly with uvicorn
   uvicorn src.app:app --reload
   ```

The API will be available at `http://localhost:8000`
- Interactive API docs: http://localhost:8000/docs
- Alternative API docs: http://localhost:8000/redoc

## API Endpoints

### Bed Management

- `GET /api/beds/current/{hospital_id}` - Get current bed availability
- `POST /api/beds/update` - Update bed counts
- `GET /api/beds/history` - View bed count history

### Hospital Management

- `GET /hospitals/` - List all hospitals
- `POST /hospitals/` - Create a new hospital
- `GET /hospitals/{hospital_id}` - Get hospital details
- `PUT /hospitals/{hospital_id}` - Update hospital information
- `DELETE /hospitals/{hospital_id}` - Delete a hospital

### Routing

- `POST /find-hospital` - Find the best hospital based on location and requirements

## Training the DRL Model

To train the Deep Reinforcement Learning model:

```bash
python -c "from src.routing.drl_environment import train_drl_model; train_drl_model()"
```

This will train the model and save it to `models/hospital_router.zip`.

## Testing

Run the test suite:
```bash
pytest tests/
```

## Project Structure

```
src/
├── app.py                # Main FastAPI application
├── database/
│   ├── __init__.py
│   └── models.py         # Database models
├── routing/
│   ├── __init__.py
│   ├── mapbox_router.py  # Mapbox Directions API integration
│   └── drl_environment.py # DRL environment and agent
└── utils/
    └── config.py         # Configuration utilities

tests/                    # Test files
.env.example             # Example environment variables
requirements.txt         # Python dependencies
README.md               # This file
```

## Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `MAPBOX_ACCESS_TOKEN` | Mapbox API access token | Yes | - |
| `DATABASE_URL` | Database connection URL | No | `sqlite:///./hospitals.db` |
| `LOG_LEVEL` | Logging level | No | `INFO` |

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Mapbox](https://www.mapbox.com/) for the mapping and directions API
- [Stable Baselines3](https://stable-baselines3.readthedocs.io/) for DRL implementation
- [FastAPI](https://fastapi.tiangolo.com/) for the web framework
