# Flight Pickup Calculator

So I got stuck waiting at the airport for like 45 minutes once because I showed up way too early, and it got me thinking - there's got to be a better way to figure this out. That's how this project started.

This thing takes your flight number and home address, then uses a bunch of APIs to figure out when you should actually leave your house. It pulls real flight data (when the plane lands), gets driving directions from Google Maps with traffic, and then runs it through some algorithms I cobbled together based on research about how long it actually takes to get through an airport.

The cool part is it lets you customize stuff - you tell it if the airport is busy, if it's a holiday, if they have checked bags, and it adjusts the calculations. The math is basically a bunch of preset multipliers and time estimates I found online, plus variables you set. It's not super robust or anything - definitely has some shortcomings and edge cases I haven't figured out yet. But hey, it works for most normal situations.

Really this was just my way of practicing full-stack development by solving a problem I actually had. Built the backend with FastAPI and the frontend with React. Planning to deploy it on Railway soon=.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Copy environment variables:
```bash
cp env.example .env
```

3. Update `.env` with your API keys

4. Run the development server:
```bash
uvicorn main:app --reload
```

## API Endpoints

- `GET /when-to-leave?flight=AA1234&address=123 Main St` - Calculate leave time
- `GET /health` - Health check

## Environment Variables

- `AVIATIONSTACK_API_KEY` - Get from https://aviationstack.com/
- `GOOGLE_MAPS_API_KEY` - Get from https://developers.google.com/maps/documentation
