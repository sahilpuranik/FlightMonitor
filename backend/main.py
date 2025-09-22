from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from datetime import datetime, timedelta
import httpx
import pytz

# load env vars
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value

load_env()

app = FastAPI(title="My Flight App", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LeaveTimeResponse(BaseModel):
    leave_time: str
    details: dict

@app.get("/when-to-leave")
async def when_to_leave(
    flight: str = Query(..., description="Flight number"),
    address: str = Query(..., description="Home address"),
    airport_busy: str = Query("medium", description="Airport busyness level"),
    holiday: str = Query("no", description="Holiday status"),
    checked_bags: str = Query("no", description="Has checked bags")
) -> LeaveTimeResponse:
    if not flight or not address:
        raise HTTPException(status_code=400, detail="Flight and address required")
    
    flight = flight.upper().strip()
    address = address.strip()
    
    # get api keys
    flight_api_key = os.getenv("AVIATIONSTACK_API_KEY")
    maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    
    flight_info = await get_flight_info(flight, flight_api_key)
    arrival_time = flight_info["arrival_time"]
    airport_name = flight_info["airport_name"]
    airport_code = flight_info["airport_code"]
    
    drive_time_minutes = await get_drive_time(address, airport_name, airport_code, maps_api_key)
    
    airport_exit_time = calculate_airport_exit_time(arrival_time, airport_busy, holiday, checked_bags)
    
    # buffer time
    buffer = 20
    leave_time = calculate_leave_time(airport_exit_time, drive_time_minutes, buffer)
    
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
async def health_check():
    return {"status": "healthy"}


async def get_flight_info(flight: str, api_key: str) -> dict:
    flightaware_key = os.getenv("FLIGHTAWARE_API_KEY")
    if flightaware_key:
        try:
            return await get_flight_info_flightaware(flight, flightaware_key)
        except Exception as e:
            print(f"FlightAware failed, falling back to AviationStack: {e}")
    
    url = "http://api.aviationstack.com/v1/flights"
    params = {"access_key": api_key, "flight_iata": flight}
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        data = response.json()
        
        flights = data.get("data", [])
        if not flights:
            raise HTTPException(status_code=404, detail="Flight not found")
        
        first_flight = flights[0]
        arrival_time = first_flight["arrival"]["scheduled"]
        airport_name = first_flight["arrival"]["airport"]
        airport_code = first_flight["arrival"]["iata"]
        
        arrival_dt = datetime.fromisoformat(arrival_time.replace('Z', '+00:00'))
        formatted_time = arrival_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        print(f"Found flight {flight} at {formatted_time} to {airport_name} ({airport_code})")
        
        return {
            "arrival_time": formatted_time,
            "airport_name": airport_name,
            "airport_code": airport_code
        }

async def get_flight_info_flightaware(flight: str, api_key: str) -> dict:
    url = f"https://aeroapi.flightaware.com/aeroapi/flights/{flight}"
    headers = {"x-apikey": api_key}
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        data = response.json()
        
        if not data.get("flights"):
            raise HTTPException(status_code=404, detail="Flight not found")
        
        flight_data = data["flights"][0]
        
        arrival_time = flight_data.get("estimated_in") or flight_data.get("scheduled_in") or flight_data.get("estimated_out") or flight_data.get("scheduled_out")
        if not arrival_time:
            raise HTTPException(status_code=404, detail="No arrival time available")
        
        destination = flight_data.get("destination", {})
        airport_name = destination.get("friendly_location") or destination.get("airport_name") or destination.get("name") or "Unknown Airport"
        airport_code = destination.get("code") or destination.get("iata") or "UNK"
        
        if airport_name == "Unknown Airport" and airport_code:
            airport_names = {
                "KSFO": "San Francisco International",
                "KJFK": "John F Kennedy International", 
                "KLAX": "Los Angeles International",
                "KORD": "Chicago O'Hare International",
                "KDFW": "Dallas Fort Worth International"
            }
            airport_name = airport_names.get(airport_code, f"Airport ({airport_code})")
        
        arrival_dt = datetime.fromisoformat(arrival_time.replace('Z', '+00:00'))
        formatted_time = arrival_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        print(f"Found flight {flight} at {formatted_time} to {airport_name} ({airport_code})")
        
        return {
            "arrival_time": formatted_time,
            "airport_name": airport_name,
            "airport_code": airport_code
        }

async def get_drive_time(address: str, airport_name: str, airport_code: str, api_key: str) -> int:
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
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        data = response.json()
        
        if data.get("status") != "OK":
            print(f"Google Maps API error: {data.get('status')}")
            return 30
        
        rows = data.get("rows", [])
        if not rows:
            print("Google Maps API: No rows found in response.")
            return 30
        
        first_row = rows[0]
        elements = first_row.get("elements", [])
        if not elements:
            print("Google Maps API: No elements found in first row.")
            return 30
        
        first_element = elements[0]
        
        if "duration_in_traffic" in first_element:
            duration_seconds = first_element["duration_in_traffic"]["value"]
            print(f"traffic time: {duration_seconds} seconds")
        elif "duration" in first_element:
            duration_seconds = first_element["duration"]["value"]
            print(f"normal time: {duration_seconds} seconds")
        else:
            print("Google Maps API: No duration or duration_in_traffic found in first element.")
            return 30
        
        duration_minutes = round(duration_seconds / 60)
        return duration_minutes

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

def get_timezone_from_address(address: str) -> str:
    address_lower = address.lower()
    
    if any(city in address_lower for city in ['new york', 'ny', 'brooklyn', 'queens', 'manhattan']):
        return "US/Eastern"
    elif any(city in address_lower for city in ['los angeles', 'la', 'san francisco', 'san diego', 'california', 'ca']):
        return "US/Pacific"
    elif any(city in address_lower for city in ['chicago', 'illinois', 'il']):
        return "US/Central"
    elif any(city in address_lower for city in ['denver', 'colorado', 'co']):
        return "US/Mountain"
    elif any(city in address_lower for city in ['miami', 'florida', 'fl', 'atlanta', 'georgia', 'ga']):
        return "US/Eastern"
    elif any(city in address_lower for city in ['seattle', 'washington', 'wa']):
        return "US/Pacific"
    else:
        return "US/Eastern"

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