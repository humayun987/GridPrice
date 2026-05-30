#!/bin/bash
echo "Running database migrations..."
alembic upgrade head
echo "Starting FastAPI server..."
python run.py
