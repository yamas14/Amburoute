"""
Main entry point for the FastAPI application.
"""
import uvicorn
import os

if __name__ == "__main__":
    # Run the FastAPI application
    uvicorn.run(
        "app:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("ENV") == "development" or os.getenv("RELOAD", "false").lower() == "true",
        log_level=os.getenv("LOG_LEVEL", "info").lower()
    )
