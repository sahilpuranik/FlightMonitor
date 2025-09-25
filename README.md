# FlightMonitor - When Should I Leave to Pick Up Someone?

A simple web app that calculates when you should leave home to pick someone up from the airport. Just enter their flight number and your address, and it tells you the perfect departure time!

## Features

- 🛫 **Real Flight Data**: Gets actual flight arrival times
- 🚗 **Live Traffic**: Uses Google Maps for current traffic conditions
- ⏰ **Smart Timing**: Accounts for airport size, holidays, and checked bags
- 🎨 **Simple Interface**: Clean, beginner-friendly design

## How It Works

1. Enter flight number (like "AA1234") and your home address
2. Select airport size, holiday status, and checked bags options
3. Get your perfect departure time with detailed breakdown

## Quick Start

### For Railway Deployment

1. Fork this repository on GitHub
2. Connect your GitHub repo to Railway
3. Add environment variables in Railway dashboard:
   - `AVIATIONSTACK_API_KEY`
   - `GOOGLE_MAPS_API_KEY`
   - `FLIGHTAWARE_API_KEY` (optional)
4. Deploy! Railway will automatically build and deploy your app

### For Local Development

1. **Clone and setup**:
```bash
git clone <your-repo-url>
cd FlightMonitor
```

2. **Install Python dependencies**:
```bash
pip install -r requirements.txt
```

3. **Setup environment**:
```bash
cp .env.example .env
# Edit .env with your API keys
```

4. **Build frontend**:
```bash
cd frontend
npm install
npm run build
cd ..
```

5. **Run the app**:
```bash
python -m uvicorn backend.main:app --reload
```

Visit http://localhost:8000 to use the app!

## Getting API Keys

- **AviationStack**: Sign up at https://aviationstack.com/ (free tier available)
- **Google Maps**: Get key at https://developers.google.com/maps/documentation
- **FlightAware**: Optional, get at https://flightaware.com/commercial/aeroapi/

## API Endpoints

- `GET /` - Web interface
- `GET /when-to-leave` - Calculate departure time
- `GET /health` - Health check

## Tech Stack

- **Backend**: FastAPI (Python)
- **Frontend**: React + Vite
- **Deployment**: Railway
- **APIs**: AviationStack, Google Maps, FlightAware
