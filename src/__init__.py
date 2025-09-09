"""
AmbuRoute - Emergency Hospital Routing System

This package provides the main application and API for the AmbuRoute system.
"""

# Import the FastAPI app to make it available when importing the package
from .app import app

__version__ = "1.0.0"
__all__ = ["app"]
