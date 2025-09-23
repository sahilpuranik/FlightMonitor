#!/bin/bash

# Install frontend dependencies and build first
cd frontend
npm install
npm run build

# Install backend dependencies
cd ../backend
pip install -r requirements.txt

# Start the backend server
uvicorn main:app --host 0.0.0.0 --port $PORT
