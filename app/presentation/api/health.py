"""
Health Check Endpoint
=====================
Simple endpoint to verify the application is running.
"""

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    """Returns the current health status of the application."""
    return {
        "status": "ok",
        "message": "Attendance Face Recognition System is running",
    }
