from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
from datetime import datetime, timedelta
import httpx
import pytz
import re

# Load environment variables for local development
def load_env():
    env_file = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value

# Load .env file if running locally
if not os.getenv("RAILWAY_ENVIRONMENT"):
    load_env()

app = FastAPI(title="FlightMonitor", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend files
frontend_path = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist')
if os.path.exists(frontend_path):
    assets_folder = os.path.join(frontend_path, "assets")
    if os.path.exists(assets_folder):
        app.mount("/assets", StaticFiles(directory=assets_folder), name="assets")

@app.get("/")
def home():
    # Serve the main page
    index_file = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist', 'index.html')
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "App not ready"}


class LeaveTimeResponse(BaseModel):
    leave_time: str
    details: dict

def check_flight_number(flight: str):
    flight = flight.upper().strip()
    flight = re.sub(r'[\s\-_]', '', flight)  # remove spaces and dashes

    # Check if it looks like a flight number (like AA123)
    if not re.match(r'^[A-Z]{2,3}\d{1,4}$', flight):
        raise HTTPException(status_code=400, detail="Please enter a valid flight number like AA123")

    return flight

def check_address(address: str):
    address = address.strip()

    if not address or len(address) < 5:
        raise HTTPException(status_code=400, detail="Please enter a valid address")

    return address

@app.get("/when-to-leave")
async def when_to_leave(
    flight: str = Query(..., description="Flight number"),
    address: str = Query(..., description="Home address"),
    airport_busy: str = Query("medium", description="Airport busyness level"),
    holiday: str = Query("no", description="Holiday status"),
    checked_bags: str = Query("no", description="Has checked bags")
) -> LeaveTimeResponse:
    # Check inputs
    flight = check_flight_number(flight)
    address = check_address(address)
    
    # Get API keys from environment
    flight_key = os.getenv("AVIATIONSTACK_API_KEY")
    maps_key = os.getenv("GOOGLE_MAPS_API_KEY")
    
    flight_info = await get_flight_info(flight, flight_key)
    arrival_time = flight_info["arrival_time"]
    airport_name = flight_info["airport_name"]
    airport_code = flight_info["airport_code"]
    
    drive_time_minutes = await get_drive_time(address, airport_name, airport_code, maps_key)
    
    airport_exit_time = calculate_airport_exit_time(arrival_time, airport_busy, holiday, checked_bags)
    
    # Extra time buffer
    extra_time = 20
    leave_time = calculate_leave_time(airport_exit_time, drive_time_minutes, extra_time)
    
    leave_time_formatted = format_time_for_user(leave_time, address)
    arrival_time_formatted = format_time_for_user(arrival_time, address)
    exit_time_formatted = format_time_for_user(airport_exit_time, address)
    
    return LeaveTimeResponse(
        leave_time=leave_time_formatted,
        details={
            "arrival_time": f"{arrival_time_formatted} at {airport_name} ({airport_code})",
            "airport_exit_time": exit_time_formatted,
            "drive_time_minutes": drive_time_minutes
        }
    )

@app.get("/health")
def health():
    return {"status": "ok"}


async def get_flight_info(flight: str, api_key: str):
    # Try FlightAware first if available
    flightaware_key = os.getenv("FLIGHTAWARE_API_KEY")
    if flightaware_key:
        try:
            return await get_flight_info_flightaware(flight, flightaware_key)
        except Exception:
            print("FlightAware failed, trying AviationStack")

    if not api_key:
        raise HTTPException(status_code=500, detail="Need flight API key")
    
    url = "http://api.aviationstack.com/v1/flights"
    params = {"access_key": api_key, "flight_iata": flight}
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=503,
                    detail="Flight data service temporarily unavailable. Please try again later."
                )
            
            data = response.json()
            
            # Check if API returned an error
            if "error" in data:
                error_msg = data["error"].get("info", "API error")
                raise HTTPException(status_code=503, detail=f"Flight API error: {error_msg}")
            
            flights = data.get("data", [])
            if not flights:
                raise HTTPException(status_code=404, detail=f"Flight {flight} not found")
            
            first_flight = flights[0]
            
            # Make sure flight has arrival info
            if not first_flight.get("arrival"):
                raise HTTPException(status_code=404, detail=f"No arrival info for flight {flight}")
            
            arrival_time = first_flight["arrival"]["scheduled"]
            airport_name = first_flight["arrival"]["airport"]
            airport_code = first_flight["arrival"]["iata"]
            
            arrival_dt = datetime.fromisoformat(arrival_time.replace('Z', '+00:00'))
            formatted_time = arrival_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            
            print(f"Flight {flight} arrives at {airport_name} at {formatted_time}")
            
            return {
                "arrival_time": formatted_time,
                "airport_name": airport_name,
                "airport_code": airport_code
            }
    
    except httpx.TimeoutException:
        raise HTTPException(status_code=503, detail="Flight API timeout")
    except Exception as e:
        print(f"Flight API error: {e}")
        raise HTTPException(status_code=503, detail="Could not get flight info")

async def get_flight_info_flightaware(flight: str, api_key: str):
    url = f"https://aeroapi.flightaware.com/aeroapi/flights/{flight}"
    headers = {"x-apikey": api_key}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        data = response.json()

        if not data.get("flights"):
            raise HTTPException(status_code=404, detail="Flight not found")

        flight_data = data["flights"][0]

        # Get arrival time
        arrival_time = (flight_data.get("estimated_in") or
                       flight_data.get("scheduled_in") or
                       flight_data.get("estimated_out") or
                       flight_data.get("scheduled_out"))
        if not arrival_time:
            raise HTTPException(status_code=404, detail="No arrival time")

        # Get airport info
        destination = flight_data.get("destination", {})
        airport_name = (destination.get("friendly_location") or
                       destination.get("airport_name") or
                       destination.get("name") or "Unknown Airport")
        airport_code = destination.get("code") or destination.get("iata") or "UNK"

        # Format the time
        arrival_dt = datetime.fromisoformat(arrival_time.replace('Z', '+00:00'))
        formatted_time = arrival_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        return {
            "arrival_time": formatted_time,
            "airport_name": airport_name,
            "airport_code": airport_code
        }

async def get_drive_time(address: str, airport_name: str, airport_code: str, api_key: str):
    if not api_key:
        print("No Google Maps key, using 30 minutes")
        return 30
    
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": address,
        "destinations": f"{airport_name} ({airport_code})",
        "key": api_key,
        "mode": "driving",
        "units": "imperial",
        "departure_time": "now",
        "traffic_model": "best_guess"
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            data = response.json()
            
            status = data.get("status")
            if status != "OK":
                print(f"Google Maps error: {status}")
                return 30
            
            rows = data.get("rows", [])
            if not rows:
                return 30

            first_row = rows[0]
            elements = first_row.get("elements", [])
            if not elements:
                return 30

            first_element = elements[0]
            element_status = first_element.get("status")

            if element_status in ["NOT_FOUND", "ZERO_RESULTS"]:
                return 30
            
            # Get drive time (with traffic if available)
            if "duration_in_traffic" in first_element:
                duration_seconds = first_element["duration_in_traffic"]["value"]
            elif "duration" in first_element:
                duration_seconds = first_element["duration"]["value"]
            else:
                return 30
            
            duration_minutes = round(duration_seconds / 60)
            return duration_minutes
    
    except Exception as e:
        print(f"Maps API error: {e}")
        return 30

def calculate_airport_exit_time(arrival_time: str, airport_busy: str, holiday: str, checked_bags: str) -> str:
    base_time = 58
    
    arrival_dt = datetime.fromisoformat(arrival_time.replace('Z', '+00:00'))
    arrival_hour = arrival_dt.hour
    
    time_multiplier = 1.0
    if 6 <= arrival_hour <= 9:
        time_multiplier = 1.3
    elif 10 <= arrival_hour <= 14:
        time_multiplier = 1.1
    elif 15 <= arrival_hour <= 18:
        time_multiplier = 1.4
    elif 19 <= arrival_hour <= 22:
        time_multiplier = 1.2
    else:
        time_multiplier = 0.8
    
    hub_multiplier = 1.0
    if airport_busy == "small-hub":
        hub_multiplier = 0.8
    elif airport_busy == "major-hub":
        hub_multiplier = 1.3
    elif airport_busy == "mega-hub":
        hub_multiplier = 1.6
    
    holiday_extra = 0
    if holiday == "small":
        holiday_extra = 15
    elif holiday == "big":
        holiday_extra = 30
    
    bag_extra = 0
    if checked_bags == "yes":
        bag_extra = 20
    
    total_minutes = int(base_time * time_multiplier * hub_multiplier) + holiday_extra + bag_extra
    exit_dt = arrival_dt + timedelta(minutes=total_minutes)
    return exit_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def calculate_leave_time(airport_exit_time: str, drive_time_minutes: int, buffer_minutes: int) -> str:
    exit_dt = datetime.fromisoformat(airport_exit_time.replace('Z', '+00:00'))
    leave_dt = exit_dt - timedelta(minutes=drive_time_minutes + buffer_minutes)
    return leave_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def get_timezone_from_address(address: str):
    address = address.lower()

    # Simple timezone guessing based on common terms
    if any(word in address for word in ['ca', 'california', 'san francisco', 'los angeles', 'seattle', 'portland']):
        return "US/Pacific"
    elif any(word in address for word in ['tx', 'texas', 'chicago', 'dallas', 'houston']):
        return "US/Central"
    elif any(word in address for word in ['co', 'colorado', 'denver', 'phoenix', 'utah']):
        return "US/Mountain"
    else:
        return "US/Eastern"  # Default

def format_time_for_user(iso_time: str, address: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
        timezone_name = get_timezone_from_address(address)
        tz = pytz.timezone(timezone_name)
        local_dt = dt.astimezone(tz)
        time_str = local_dt.strftime("%I:%M %p").lstrip('0')
        tz_abbr = local_dt.strftime("%Z")
        return f"{time_str} {tz_abbr}"
    except Exception:
        return iso_time