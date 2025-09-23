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

# load env vars (only if .env file exists)
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value

# Only load .env file if running locally
if os.getenv("RAILWAY_ENVIRONMENT") is None:
    load_env()

app = FastAPI(title="My Flight App", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files from frontend build
# Try multiple possible locations for the frontend build
possible_paths = [
    os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist'),  # Relative from backend
    os.path.join(os.getcwd(), 'frontend', 'dist'),  # From project root
    '/app/frontend/dist',  # Absolute path in Railway
    './frontend/dist',  # Relative from project root
]

frontend_dist = None
for path in possible_paths:
    print(f"Checking path: {path}")
    if os.path.exists(path):
        frontend_dist = path
        print(f"Found frontend dist at: {frontend_dist}")
        break

if frontend_dist and os.path.exists(frontend_dist):
    app.mount("/static", StaticFiles(directory=frontend_dist), name="static")
    print("Mounted static files")

@app.get("/")
async def serve_frontend():
    """Serve the React frontend"""
    # Try to find index.html in multiple locations
    possible_index_paths = [
        os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist', 'index.html'),
        os.path.join(os.getcwd(), 'frontend', 'dist', 'index.html'),
        '/app/frontend/dist/index.html',
        './frontend/dist/index.html',
    ]
    
    for frontend_path in possible_index_paths:
        print(f"Looking for index.html at: {frontend_path}")
        if os.path.exists(frontend_path):
            print(f"Found index.html at: {frontend_path}")
            return FileResponse(frontend_path)
    
    # If none found, show debug info
    print("Index.html not found in any location")
    return {
        "message": "Frontend not built yet", 
        "debug_paths": possible_index_paths,
        "current_working_dir": os.getcwd(),
        "backend_file_location": __file__
    }

class LeaveTimeResponse(BaseModel):
    leave_time: str
    details: dict

def validate_flight_number(flight: str) -> str:
    """Validate and normalize flight number format"""
    flight = flight.upper().strip()
    
    # Remove spaces and common separators
    flight = re.sub(r'[\s\-_]', '', flight)
    
    # Basic regex for airline code + flight number
    if not re.match(r'^[A-Z]{2,3}\d{1,4}$', flight):
        raise HTTPException(
            status_code=400, 
            detail="Invalid flight number format. Use format like 'AA123' or 'UA456'"
        )
    
    return flight

def validate_address(address: str) -> str:
    """Basic address validation"""
    address = address.strip()
    
    if not address or len(address) < 5:
        raise HTTPException(
            status_code=400,
            detail="Please enter a valid address (at least 5 characters)"
        )
    
    return address

@app.get("/when-to-leave")
async def when_to_leave(
    flight: str = Query(..., description="Flight number"),
    address: str = Query(..., description="Home address"),
    airport_busy: str = Query("medium", description="Airport busyness level"),
    holiday: str = Query("no", description="Holiday status"),
    checked_bags: str = Query("no", description="Has checked bags")
) -> LeaveTimeResponse:
    # Input validation
    try:
        flight = validate_flight_number(flight)
        address = validate_address(address)
    except HTTPException:
        raise
    
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
    
    if not api_key:
        raise HTTPException(
            status_code=500, 
            detail="Flight API not configured. Please check your API keys."
        )
    
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
            
            # Check for API errors
            if "error" in data:
                error_msg = data["error"].get("info", "Unknown API error")
                raise HTTPException(
                    status_code=503,
                    detail=f"Flight API error: {error_msg}"
                )
            
            flights = data.get("data", [])
            if not flights:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Flight {flight} not found. Please check the flight number and try again."
                )
            
            first_flight = flights[0]
            
            # Check if flight has arrival info
            if not first_flight.get("arrival"):
                raise HTTPException(
                    status_code=404,
                    detail=f"Flight {flight} found but no arrival information available."
                )
            
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
    
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=503,
            detail="Flight data request timed out. Please try again."
        )
    except Exception as e:
        print(f"Unexpected error getting flight info: {e}")
        raise HTTPException(
            status_code=503,
            detail="Unable to get flight information. Please try again later."
        )

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
    if not api_key:
        print("Google Maps API key not configured, using default drive time")
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
            if status == "REQUEST_DENIED":
                print("Google Maps API: Request denied - check API key")
                return 30
            elif status == "OVER_QUERY_LIMIT":
                print("Google Maps API: Over query limit")
                return 30
            elif status == "INVALID_REQUEST":
                print("Google Maps API: Invalid request")
                return 30
            elif status != "OK":
                print(f"Google Maps API error: {status}")
                return 30
            
            rows = data.get("rows", [])
            if not rows:
                print("Google Maps API: No rows found in response")
                return 30
            
            first_row = rows[0]
            elements = first_row.get("elements", [])
            if not elements:
                print("Google Maps API: No elements found in first row")
                return 30
            
            first_element = elements[0]
            element_status = first_element.get("status")
            
            if element_status == "NOT_FOUND":
                print("Google Maps API: Address not found")
                return 30
            elif element_status == "ZERO_RESULTS":
                print("Google Maps API: No route found")
                return 30
            
            if "duration_in_traffic" in first_element:
                duration_seconds = first_element["duration_in_traffic"]["value"]
                print(f"traffic time: {duration_seconds} seconds")
            elif "duration" in first_element:
                duration_seconds = first_element["duration"]["value"]
                print(f"normal time: {duration_seconds} seconds")
            else:
                print("Google Maps API: No duration found")
                return 30
            
            duration_minutes = round(duration_seconds / 60)
            return duration_minutes
    
    except httpx.TimeoutException:
        print("Google Maps API: Request timed out")
        return 30
    except Exception as e:
        print(f"Google Maps API error: {e}")
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

def get_timezone_from_address(address: str) -> str:
    address_lower = address.lower()
    
    # Check for ZIP codes first (more reliable)
    zip_match = re.search(r'\b(\d{5})\b', address)
    if zip_match:
        zip_code = int(zip_match.group(1))
        if 1000 <= zip_code <= 5999:  # Eastern (ME, NH, VT, MA, RI, CT, NY, NJ, PA, etc.)
            return "US/Eastern"
        elif 6000 <= zip_code <= 7999:  # Central (IL, WI, MN, IA, MO, AR, LA, etc.)
            return "US/Central"
        elif 8000 <= zip_code <= 8999:  # Mountain (CO, WY, MT, ND, SD, NE, KS, NM, UT, etc.)
            return "US/Mountain"
        elif 9000 <= zip_code <= 9999:  # Pacific (CA, NV, OR, WA, etc.)
            return "US/Pacific"
    
    # City/state matching (fallback)
    eastern_cities = [
        'new york', 'ny', 'brooklyn', 'queens', 'manhattan', 'bronx', 'staten island',
        'boston', 'philadelphia', 'washington', 'dc', 'atlanta', 'miami', 'florida', 'fl',
        'charlotte', 'raleigh', 'richmond', 'baltimore', 'pittsburgh', 'cleveland',
        'columbus', 'cincinnati', 'louisville', 'nashville', 'memphis', 'birmingham',
        'jacksonville', 'orlando', 'tampa', 'fort lauderdale', 'west palm beach'
    ]
    
    pacific_cities = [
        'los angeles', 'la', 'san francisco', 'san diego', 'california', 'ca',
        'seattle', 'portland', 'washington', 'wa', 'oregon', 'or', 'nevada', 'nv',
        'las vegas', 'reno', 'sacramento', 'fresno', 'long beach', 'oakland',
        'san jose', 'anaheim', 'santa ana', 'riverside', 'stockton', 'irvine'
    ]
    
    central_cities = [
        'chicago', 'illinois', 'il', 'houston', 'dallas', 'austin', 'texas', 'tx',
        'san antonio', 'fort worth', 'el paso', 'arlington', 'corpus christi',
        'plano', 'laredo', 'lubbock', 'madison', 'wisconsin', 'wi', 'minneapolis',
        'minnesota', 'mn', 'st paul', 'kansas city', 'missouri', 'mo', 'st louis',
        'milwaukee', 'detroit', 'michigan', 'mi', 'grand rapids', 'warren',
        'new orleans', 'louisiana', 'la', 'baton rouge', 'shreveport'
    ]
    
    mountain_cities = [
        'denver', 'colorado', 'co', 'phoenix', 'arizona', 'az', 'tucson', 'mesa',
        'chandler', 'glendale', 'scottsdale', 'gilbert', 'tempe', 'peoria',
        'salt lake city', 'utah', 'ut', 'west valley city', 'provo', 'west jordan',
        'orem', 'sandy', 'ogden', 'st george', 'layton', 'taylorsville',
        'albuquerque', 'new mexico', 'nm', 'las cruces', 'rio rancho', 'santa fe',
        'billings', 'montana', 'mt', 'missoula', 'great falls', 'bozeman',
        'cheyenne', 'wyoming', 'wy', 'casper', 'laramie', 'gillette'
    ]
    
    if any(city in address_lower for city in eastern_cities):
        return "US/Eastern"
    elif any(city in address_lower for city in pacific_cities):
        return "US/Pacific"
    elif any(city in address_lower for city in central_cities):
        return "US/Central"
    elif any(city in address_lower for city in mountain_cities):
        return "US/Mountain"
    else:
        # Default to Eastern for unknown locations
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