# Copyright 2026 Google LLC
# Seed script for travel-planner Firestore database

from google.cloud import firestore

# Hardcode project ID to prevent Agent Engine returning project number
FIRESTORE_PROJECT = "qwiklabs-gcp-04-7aadac52ffe0"

DESTINATIONS = [
    {
        "id": "kyoto-japan",
        "name": "Kyoto",
        "country": "Japan",
        "region": "East Asia",
        "vibe": "Cultural, Historic, Scenic",
        "best_season": "Spring (Cherry Blossoms) or Autumn (Foliage)",
        "budget_level": "$$",
        "top_attractions": [
            "Fushimi Inari Taisha",
            "Kinkaku-ji (Golden Pavilion)",
            "Arashiyama Bamboo Grove",
            "Gion Geisha District"
        ],
        "local_cuisine": ["Matcha Parfait", "Kaiseki Ryori", "Yudofu"],
        "description": "The historic heart of Japan featuring thousands of classical Buddhist temples, gardens, imperial palaces, and traditional wooden houses."
    },
    {
        "id": "amalfi-coast-italy",
        "name": "Amalfi Coast",
        "country": "Italy",
        "region": "Southern Europe",
        "vibe": "Romantic, Coastal, Scenic",
        "best_season": "May to September",
        "budget_level": "$$$",
        "top_attractions": [
            "Positano Cliffside Village",
            "Villa Cimbrone Gardens in Ravello",
            "Path of the Gods Hike",
            "Capri Day Cruise"
        ],
        "local_cuisine": ["Limoncello", "Scialatielli ai Frutti di Mare", "Delizia al Limone"],
        "description": "A stunning 50-kilometer stretch of coastline in southern Italy known for dramatic sheer cliffs, pastel-colored fishing villages, and terraced lemon groves."
    },
    {
        "id": "banff-canada",
        "name": "Banff National Park",
        "country": "Canada",
        "region": "North America",
        "vibe": "Adventure, Alpine, Nature",
        "best_season": "June to August (Hiking) or Dec to March (Skiing)",
        "budget_level": "$$",
        "top_attractions": [
            "Lake Louise",
            "Moraine Lake",
            "Icefields Parkway",
            "Banff Gondola & Sulphur Mountain"
        ],
        "local_cuisine": ["Alberta Bison Burger", "Poutine", "BeaverTails"],
        "description": "Canada's oldest national park nestled in the heart of the Rocky Mountains, featuring turquoise glacial lakes, jagged peaks, and abundant wildlife."
    },
    {
        "id": "oaxaca-mexico",
        "name": "Oaxaca City",
        "country": "Mexico",
        "region": "Latin America",
        "vibe": "Culinary, Arts, Indigenous Heritage",
        "best_season": "October to March",
        "budget_level": "$",
        "top_attractions": [
            "Monte Albán Zapotec Ruins",
            "Templo de Santo Domingo",
            "Hierve el Agua Petrified Waterfalls",
            "Mercado 20 de Noviembre"
        ],
        "local_cuisine": ["Mole Negro", "Tlayudas", "Artisanal Mezcal", "Chapulines"],
        "description": "The culinary capital of Mexico celebrated for world-famous moles, mezcal distilleries, vibrant indigenous textiles, and colonial architecture."
    }
]

def seed_database():
    print(f"Connecting to Firestore in project: {FIRESTORE_PROJECT}...")
    db = firestore.Client(project=FIRESTORE_PROJECT)
    collection = db.collection("destinations")

    for dest in DESTINATIONS:
        doc_id = dest["id"]
        doc_ref = collection.document(doc_id)
        doc_ref.set(dest)
        print(f"  ✓ Seeded destination: {dest['name']} ({dest['country']}) -> ID: {doc_id}")

    print("\nSuccessfully seeded Firestore destinations collection! 🎉")

if __name__ == "__main__":
    seed_database()
