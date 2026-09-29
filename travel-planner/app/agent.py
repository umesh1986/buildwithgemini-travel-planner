# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import os
from zoneinfo import ZoneInfo


import requests
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
try:
    from a2ui.basic_catalog.provider import BasicCatalog
    from a2ui.schema.manager import A2uiSchemaManager
except ImportError:
    BasicCatalog = None
    A2uiSchemaManager = None

from app.a2ui_utils import a2ui_callback
from google.genai import types




from google.cloud import firestore, storage



MODEL = "gemini-2.5-flash"

# Hardcode project ID explicitly to avoid Agent Engine returning the project number
FIRESTORE_PROJECT = "qwiklabs-gcp-04-7aadac52ffe0"
db = firestore.Client(project=FIRESTORE_PROJECT)

# Hardcode Cloud Storage bucket name for public assets
GCS_BUCKET_NAME = "travel-planner-media-qwiklabs-gcp-04-7aadac52ffe0"
storage_client = storage.Client(project=FIRESTORE_PROJECT)
image_client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT, location="global")

# Reasoning Engine resource from deployment_metadata.json
AGENT_ENGINE_RESOURCE = "projects/562964563406/locations/us-central1/reasoningEngines/7112529064094597120"
sandbox_code_executor = AgentEngineSandboxCodeExecutor(agent_engine_resource_name=AGENT_ENGINE_RESOURCE)



def list_destinations() -> list[dict]:
    """Retrieves all destinations available in the travel catalog.

    Returns:
        A list of destination records including name, country, vibe, budget, and top attractions.
    """
    destinations = []
    docs = db.collection("destinations").stream()
    for doc in docs:
        destinations.append(doc.to_dict())
    return destinations


def search_destinations(query: str) -> list[dict]:
    """Searches the destination catalog by name, country, vibe, or attraction keywords.

    Args:
        query: The search term (e.g., 'Japan', 'coastal', 'hiking', 'culinary', 'historic').

    Returns:
        A list of matching destinations.
    """
    query_lower = query.lower()
    matches = []
    docs = db.collection("destinations").stream()
    for doc in docs:
        data = doc.to_dict()
        searchable_text = f"{data.get('name', '')} {data.get('country', '')} {data.get('vibe', '')} {data.get('description', '')} {' '.join(data.get('top_attractions', []))}".lower()
        if query_lower in searchable_text:
            matches.append(data)
    return matches


def get_destination_details(destination_id: str) -> dict:
    """Retrieves detailed information for a specific destination by its ID.

    Args:
        destination_id: The unique slug ID of the destination (e.g. 'kyoto-japan', 'amalfi-coast-italy').

    Returns:
        The full destination record dictionary or an error message if not found.
    """
    doc_ref = db.collection("destinations").document(destination_id.lower().strip())
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict()
    return {"error": f"Destination with ID '{destination_id}' was not found in the catalog."}


def add_destination(
    name: str,
    country: str,
    region: str,
    vibe: str,
    best_season: str,
    budget_level: str,
    top_attractions: list[str],
    local_cuisine: list[str],
    description: str,
) -> dict:
    """Adds a new destination recommendation to the travel catalog.

    Args:
        name: Name of the city, region, or park (e.g., 'Reykjavik').
        country: Country (e.g., 'Iceland').
        region: Geographic region (e.g., 'Northern Europe').
        vibe: Keywords describing atmosphere (e.g., 'Geothermal, Nordic, Aurora').
        best_season: Recommended time of year to visit.
        budget_level: Relative cost scale ('$', '$$', or '$$$').
        top_attractions: List of landmark or excursion names.
        local_cuisine: List of traditional foods or drinks.
        description: A short overview of the destination.

    Returns:
        A confirmation dictionary with the newly created destination ID and status.
    """
    doc_id = f"{name.lower().replace(' ', '-')}-{country.lower().replace(' ', '-')}"
    record = {
        "id": doc_id,
        "name": name,
        "country": country,
        "region": region,
        "vibe": vibe,
        "best_season": best_season,
        "budget_level": budget_level,
        "top_attractions": top_attractions,
        "local_cuisine": local_cuisine,
        "description": description,
    }
    db.collection("destinations").document(doc_id).set(record)
    return {"status": "success", "message": f"Added destination '{name}' to the catalog.", "destination_id": doc_id}


def get_weather(location: str) -> str:
    """Fetches real-time weather conditions for any travel destination or city worldwide.

    Args:
        location: City, region, or destination name (e.g. 'Kyoto', 'Paris', 'Queenstown').

    Returns:
        A concise summary of current temperature, weather conditions, and wind speed.
    """
    try:
        geo_resp = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": location, "count": 1, "language": "en", "format": "json"},
            timeout=5,
        ).json()
        results = geo_resp.get("results")
        if not results:
            return f"Could not find coordinates for location: '{location}'."

        place = results[0]
        lat, lon = place["latitude"], place["longitude"]
        place_name = place.get("name", location)
        country = place.get("country", "")

        weather_resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": lat, "longitude": lon, "current": "temperature_2m,weather_code,wind_speed_10m"},
            timeout=5,
        ).json()
        current = weather_resp.get("current", {})
        temp_c = current.get("temperature_2m")
        wind = current.get("wind_speed_10m")
        temp_f = round((temp_c * 9 / 5) + 32, 1) if temp_c is not None else None

        weather_codes = {
            0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Foggy", 48: "Depositing rime fog", 51: "Light drizzle", 53: "Moderate drizzle",
            61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain", 71: "Slight snow",
            73: "Moderate snow", 75: "Heavy snow", 95: "Thunderstorm"
        }
        condition = weather_codes.get(current.get("weather_code"), "Fair")

        return f"{place_name}, {country}: {condition}, {temp_c}°C ({temp_f}°F), Wind: {wind} km/h."
    except Exception as e:
        return f"Unable to fetch live weather for '{location}': {str(e)}"



def get_current_time(query: str) -> str:
    """Gets the current local time for a travel location.

    Args:
        query: City or country name.

    Returns:
        Current time string with timezone.
    """
    q = query.lower()
    if "kyoto" in q or "japan" in q:
        tz = ZoneInfo("Asia/Tokyo")
    elif "amalfi" in q or "italy" in q:
        tz = ZoneInfo("Europe/Rome")
    elif "banff" in q or "canada" in q:
        tz = ZoneInfo("America/Edmonton")
    elif "oaxaca" in q or "mexico" in q:
        tz = ZoneInfo("America/Mexico_City")
    else:
        tz = ZoneInfo("UTC")

    now = datetime.datetime.now(tz)
    return f"Current local time in {query} is {now.strftime('%A, %b %d, %Y %I:%M %p %Z')}"


def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    """Converts a budget or price from one currency to another using real-time exchange rates.

    Args:
        amount: The monetary amount to convert (e.g. 150.0).
        from_currency: 3-letter currency code (e.g. 'USD', 'EUR', 'JPY', 'GBP', 'CAD', 'MXN').
        to_currency: Target 3-letter currency code (e.g. 'JPY', 'EUR', 'USD').

    Returns:
        A formatted string with the converted amount and current exchange rate.
    """
    from_curr = from_currency.upper().strip()
    to_curr = to_currency.upper().strip()
    try:
        url = f"https://open.er-api.com/v6/latest/{from_curr}"
        resp = requests.get(url, timeout=5).json()
        if resp.get("result") != "success":
            return f"Error fetching exchange rates for base currency {from_curr}."

        rates = resp.get("rates", {})
        rate = rates.get(to_curr)
        if rate is None:
            return f"Currency code '{to_curr}' is not supported or recognized."

        converted = round(amount * rate, 2)
        return f"{amount:,.2f} {from_curr} = {converted:,.2f} {to_curr} (Rate: 1 {from_curr} = {rate:.4f} {to_curr})"
    except Exception as e:
        return f"Failed to perform currency conversion: {str(e)}"


def geocode_address(address: str) -> dict:
    """Converts a street address, landmark, or location query into geographic coordinates using the Google Maps Geocoding API.

    Args:
        address: The address or place to geocode (e.g., '1600 Amphitheatre Pkwy, Mountain View, CA' or 'Eiffel Tower, Paris').

    Returns:
        A dictionary containing the formatted address and latitude/longitude coordinates.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key or api_key == "PASTE_KEY_HERE":
        return {"error": "GOOGLE_MAPS_API_KEY environment variable is not set or contains placeholder value."}

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    try:
        resp = requests.get(url, params={"address": address, "key": api_key}, timeout=8)
        data = resp.json()
        status = data.get("status")
        if status != "OK":
            return {"error": f"Geocoding API error: {status}", "details": data.get("error_message")}

        results = data.get("results", [])
        if not results:
            return {"error": f"No coordinates found for address: {address}"}

        first = results[0]
        loc = first.get("geometry", {}).get("location", {})
        return {
            "address": first.get("formatted_address"),
            "latitude": loc.get("lat"),
            "longitude": loc.get("lng"),
            "place_id": first.get("place_id"),
        }
    except Exception as e:
        return {"error": f"Failed to call Geocoding API: {str(e)}"}


def find_nearby_places(latitude: float, longitude: float, place_type: str, radius_meters: float = 1500.0) -> list[dict]:
    """Finds nearby places of a specific type around a location using the Google Maps Places API (New).

    Args:
        latitude: Latitude of the center point (e.g. 35.0116).
        longitude: Longitude of the center point (e.g. 135.7681).
        place_type: Standard place type (e.g. 'restaurant', 'cafe', 'tourist_attraction', 'museum', 'lodging', 'park').
        radius_meters: Search radius in meters (default 1500m, max 50000m).

    Returns:
        A list of matching places with name, formatted address, and location coordinates.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key or api_key == "PASTE_KEY_HERE":
        return [{"error": "GOOGLE_MAPS_API_KEY environment variable is not set or contains placeholder value."}]

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.types",
    }
    payload = {
        "includedTypes": [place_type.lower().strip()],
        "maxResultCount": 5,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": latitude, "longitude": longitude},
                "radius": min(radius_meters, 50000.0),
            }
        },
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=8)
        if resp.status_code != 200:
            return [{"error": f"Places API error: HTTP {resp.status_code}", "details": resp.text}]

        data = resp.json()
        places_out = []
        for p in data.get("places", []):
            display_name = p.get("displayName", {}).get("text", "")
            places_out.append({
                "name": display_name,
                "address": p.get("formattedAddress", ""),
                "location": p.get("location", {}),
            })
        return places_out or [{"message": f"No places of type '{place_type}' found within {radius_meters}m."}]
    except Exception as e:
        return [{"error": f"Failed to call Places API: {str(e)}"}]


async def generate_destination_image(
    prompt: str,
    destination_name: str,
    tool_context: ToolContext,
) -> dict:
    """Generates an illustration, postcard, or landmark visual for a destination using gemini-3.1-flash-lite-image.

    Saves the image into the session's artifacts panel and uploads it to the public Cloud Storage bucket.

    Args:
        prompt: Description of the scene or illustration to create (e.g. 'A vintage travel postcard of Kyoto pagodas in spring').
        destination_name: Name of the destination (e.g. 'Kyoto', 'Amalfi Coast').
        tool_context: ADK ToolContext injected automatically by the framework.

    Returns:
        A dictionary with the public HTTPS URL, the saved artifact filename, and status.
    """
    try:
        response = image_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
        )
        if not response.candidates or not response.candidates[0].content.parts:
            return {"error": "No image content returned by model."}

        part = response.candidates[0].content.parts[0]
        inline_blob = getattr(part, "inline_data", None)
        if not inline_blob or not inline_blob.data:
            return {"error": "Image bytes not found in model response."}

        image_bytes = inline_blob.data
        mime_type = inline_blob.mime_type or "image/jpeg"
        extension = "jpg" if "jpeg" in mime_type else "png"

        clean_name = destination_name.lower().replace(" ", "_")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{clean_name}_{timestamp}.{extension}"

        # 1. Save artifact into the session (shows in Playground's Artifacts panel)
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        try:
            await tool_context.save_artifact(filename, artifact_part)
        except Exception as artifact_err:
            print(f"Warning: could not save artifact to session context: {artifact_err}")

        # 2. Upload bytes directly to Cloud Storage bucket without local files
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"
        return {
            "status": "success",
            "destination": destination_name,
            "artifact_filename": filename,
            "public_url": public_url,
        }
    except Exception as e:
        return {"error": f"Failed to generate destination image: {str(e)}"}


async def generate_destination_video(
    prompt: str,
    destination_name: str,
    tool_context: ToolContext,
) -> dict:
    """Generates a short travel video for a destination or attraction using Google's Omni model (gemini-omni-flash-preview).

    Saves the video with tool_context.save_artifact so it appears in the Playground's Artifacts panel,
    and uploads the video bytes directly to the public Cloud Storage bucket, returning its public HTTPS URL.

    Args:
        prompt: Description of the scene or short travel clip to generate (e.g. 'A scenic aerial drone view of Kyoto temples surrounded by blooming cherry blossoms').
        destination_name: Name of the destination or attraction (e.g. 'Kyoto', 'Amalfi Coast').
        tool_context: ADK ToolContext injected automatically by the framework.

    Returns:
        A dictionary containing the public HTTPS URL (https://storage.googleapis.com/<bucket>/<object>), the artifact filename, and status.
    """
    try:
        # Use gemini-omni-flash-preview in global region
        interaction = image_client.interactions.create(
            model="gemini-omni-flash-preview",
            input=prompt,
        )

        output_video = getattr(interaction, "output_video", None)
        if not output_video:
            # Fallback inspection of steps
            steps = getattr(interaction, "steps", []) or []
            for step in reversed(steps):
                if getattr(step, "type", None) == "model_output":
                    content = getattr(step, "content", []) or []
                    for item in reversed(content):
                        if getattr(item, "type", None) == "video":
                            output_video = item
                            break
                if output_video:
                    break

        if not output_video:
            return {"error": "No video returned by gemini-omni-flash-preview model."}

        raw_data = getattr(output_video, "data", None)
        if not raw_data:
            return {"error": "Video data bytes not found in model output."}

        video_bytes = base64.b64decode(raw_data) if isinstance(raw_data, str) else raw_data
        mime_type = getattr(output_video, "mime_type", None) or "video/mp4"

        clean_name = destination_name.lower().replace(" ", "_")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{clean_name}_video_{timestamp}.mp4"

        # 1. Save artifact into the session (shows in Playground's Artifacts panel)
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        try:
            await tool_context.save_artifact(filename, artifact_part)
        except Exception as artifact_err:
            print(f"Warning: could not save video artifact to session context: {artifact_err}")

        # 2. Upload video bytes to Cloud Storage bucket without local files
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"
        return {
            "status": "success",
            "destination": destination_name,
            "artifact_filename": filename,
            "public_url": public_url,
        }
    except Exception as e:
        return {"error": f"Failed to generate destination video: {str(e)}"}



async def generate_memories_callback(callback_context: CallbackContext):
    """WRITE: after each turn, send the session to Memory Bank for extraction."""
    await callback_context.add_session_to_memory()
    return None


_PROMPT_FILE = os.path.join(os.path.dirname(__file__), "a2ui_prompt.txt")

if A2uiSchemaManager and BasicCatalog:
    schema_manager = A2uiSchemaManager(
        version="0.8",
        catalogs=[BasicCatalog.get_config("0.8")],
    )

    instruction = schema_manager.generate_system_prompt(
        role_description=(
            "You are an expert travel planner assistant. You help travelers discover destinations, "
            "explore curated spots, check live weather, convert currencies, geocode locations, find nearby attractions, "
            "generate visual destination postcards, calculate trip budgets, and plan itineraries.\n\n"
            "You remember and honor all user allergies (food allergies, drug/medical allergies, environmental sensitivities), "
            "dietary restrictions, and preferences from previous conversations. Whenever recommending restaurants, "
            "food experiences, destinations, or activities, always verify and cross-check against all remembered user allergies "
            "to keep travelers safe and personalize your recommendations.\n\n"
            "You have access to a secure Python sandbox environment powered by AgentEngineSandboxCodeExecutor. "
            "Whenever a traveler asks for date arithmetic (e.g., number of days or weeks between travel dates), "
            "compound interest, custom budget division, exchange simulations, or data analysis, write executable "
            "Python code wrapped in ```python ... ``` blocks. Your Python code will be executed automatically in the sandbox "
            "and the output returned to you."
        ),
        workflow_description="Analyze the request and return structured UI when appropriate.",
        ui_description=(
            "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
            "Never nest a Card inside a Card. "
            "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
            "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
            "nothing in adk web). "
            "You may include one Image component, but only when you have a public https "
            "URL for the image (for example the URL an image tool returns after uploading "
            "to a public bucket). Set the Image url to that exact https link, for example "
            "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
            "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
            "not have a public URL, add a short Text line noting the image instead. "
            "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
            "headings and emphasis. "
            "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
            "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
        ),
        include_schema=True,
        include_examples=True,
    )
elif os.path.exists(_PROMPT_FILE):
    with open(_PROMPT_FILE) as f:
        instruction = f.read()
else:
    instruction = (
        "You are an expert travel planner assistant. You help travelers discover destinations, "
        "explore curated spots, check live weather, convert currencies, geocode locations, find nearby attractions, "
        "generate visual destination postcards, calculate trip budgets, and plan itineraries."
    )



root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    code_executor=sandbox_code_executor,
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
    tools=[
        PreloadMemoryTool(),
        list_destinations,
        search_destinations,
        get_destination_details,
        add_destination,
        get_weather,
        get_current_time,
        convert_currency,
        geocode_address,
        find_nearby_places,
        generate_destination_image,
        generate_destination_video,
    ],

)


app = App(
    root_agent=root_agent,
    name="app",
)



