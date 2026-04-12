#!/bin/bash
# Startup script for Azure App Service
# Ensures the app runs from wwwroot where all source files (including agents/) live

cd /home/site/wwwroot

# Activate the virtual environment created by Oryx
if [ -d "antenv" ]; then
    source antenv/bin/activate
fi

# Start gunicorn with uvicorn workers
gunicorn -w 1 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:8000
