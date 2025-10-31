from flask import Flask, request, jsonify, make_response
import requests, random, math

app = Flask(__name__)

# ---------------- CONFIG ----------------
# NOTE: Replace with your actual Geoapify API key
GEOAPIFY_KEY = "ecd717b7a44b4050b904f610ee762e8b"

# ---------------- HELPER FUNCTIONS ----------------

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def geoapify_geocode(place):
    url = "https://api.geoapify.com/v1/geocode/search"
    params = {"text": f"{place}, India", "apiKey": GEOAPIFY_KEY}
    try:
        res = requests.get(url, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
        if "results" in data and data["results"]:
            return float(data["results"][0]["lat"]), float(data["results"][0]["lon"])
        elif "features" in data and data["features"]:
            coords = data["features"][0]["geometry"]["coordinates"]
            return float(coords[1]), float(coords[0])
    except Exception as e:
        print("❌ Geocode error:", e)
    return None, None

def geoapify_places(lat, lon, categories, radius=15000, limit=30):
    url = "https://api.geoapify.com/v2/places"
    params = {
        "categories": ",".join(categories),
        "filter": f"circle:{lon},{lat},{radius}",
        "bias": f"proximity:{lon},{lat}",
        "limit": limit,
        "apiKey": GEOAPIFY_KEY
    }
    try:
        res = requests.get(url, params=params, timeout=15)
        res.raise_for_status()
        feats = res.json().get("features", [])
        out = []
        for f in feats:
            p = f.get("properties", {})
            if not p.get("name"): continue
            # Geoapify might return coordinates in the properties or the geometry
            latp = p.get("lat") or f["geometry"]["coordinates"][1]
            lonp = p.get("lon") or f["geometry"]["coordinates"][0]
            
            # Standardized Map URL (using example for demonstration)
            map_url = f"https://www.google.com/maps/search/?api=1&query={latp},{lonp}"

            out.append({
                "name": p["name"],
                "address": p.get("formatted",""),
                "map_url": map_url
            })
        return out
    except Exception as e:
        print("⚠️ Geoapify error:", e)
        return []

def wikipedia_fallback(region):
    try:
        url = "https://en.wikipedia.org/w/rest.php/v1/search/title"
        params = {"q": f"Tourist attractions in {region} India", "limit": 10}
        headers = {"User-Agent": "TripPlannerBot/1.0"}
        r = requests.get(url, params=params, headers=headers, timeout=10)
        pages = r.json().get("pages", [])
        return [{"name": p["title"], "address": region, "map_url": f"https://en.wikipedia.org/wiki/{p['title']}"} for p in pages]
    except:
        return []

def mood_stays(lat, lon, mood):
    mood = mood.lower().strip()

    # --- 1. Define Price Range and Categories (Corrected Logic) ---
    if mood in ["relaxed", "cultural"]:
        price_range = (5000, 25000) # High-Value: ₹5,000 to ₹25,000
        mood_categories = {
            "relaxed": ["accommodation.resort", "accommodation.hotel"],
            "cultural": ["accommodation.home_stay", "accommodation.guest_house", "accommodation.apartment"]
        }.get(mood)
    else: 
        price_range = (800, 7000) # Low-Value: ₹800 to ₹7,000
        mood_categories = {
            "adventurous": ["accommodation.hostel","camping"],
            "spiritual": ["accommodation.lodge", "accommodation.guest_house"]
        }.get(mood)
    
    # Define a default category list for safety
    mood_categories = mood_categories or ["accommodation.hotel"] 
    broad_fallback_category = ["accommodation"] 

    # --- 2. Execute Primary Search ---
    stays = geoapify_places(lat, lon, mood_categories)
    
    # --- 3. Execute Fallback Search if needed ---
    if not stays:
        print(f"DEBUG: No specific '{mood}' stays found. Trying broad accommodation search.")
        stays = geoapify_places(lat, lon, broad_fallback_category)
        
    # --- 4. Apply Pricing and Tier Classification to all real results ---
    for s in stays:
        # Assign a random price within the MOOD's determined range
        s["price_inr"] = random.randint(*price_range)
        
        # Assign Tier based on the price. Tiers are consistent regardless of mood.
        if s["price_inr"] < 2500:
            s["tier"] = "Budget"
        elif s["price_inr"] < 10000:
            s["tier"] = "Mid-range"
        else:
            s["tier"] = "Luxury"
    
    # --- 5. Final Fallback if still no results (Very unlikely) ---
    if not stays: 
        print(f"DEBUG: Broad search also failed. Returning default stay.")
        default_price = random.randint(*price_range)
        default_tier = "Budget" if default_price < 2500 else "Mid-range" if default_price < 10000 else "Luxury"
        stays = [{
            "name": f"Default {mood.title()} Stay (No Geoapify Results)", 
            "address": "City Center",
            "price_inr": default_price,
            "tier": default_tier,
            "map_url": f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
        }]
    
    return stays[:5] # Limit to top 5 results

def estimate_cost(days, avg_price):
    food = round(avg_price*0.3)
    travel = random.randint(500,2000)
    return {
        "stay_per_day": avg_price,
        "food_per_day": food,
        "travel_per_day": travel,
        "total_inr": (avg_price+food+travel)*days
    }
    
# ---------------- FLASK ROUTES ----------------

# HTML Content (Combined Frontend - NO CHANGES HERE)
HTML_CONTENT = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>India Trip Planner</title>
<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
  min-height: 100vh;
  overflow-x: hidden;
}

.page {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: none;
  align-items: center;
  justify-content: center;
  transition: opacity 0.5s ease;
}

.page.active {
  display: flex;
  animation: fadeIn 0.8s ease;
}

.page::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 1;
}

/* Welcome Page */
#welcomePage {
  background: url('https://images.unsplash.com/photo-1524492412937-b28074a5d7da?w=1920&q=80') center/cover;
}

/* Region Page */
#regionPage {
  background: url('https://images.unsplash.com/photo-1587474260584-136574528ed5?w=1920&q=80') center/cover;
}

/* Days Page */
#daysPage {
  background: url('https://images.unsplash.com/photo-1548013146-72479768bada?w=1920&q=80') center/cover;
}

/* Mood Page */
#moodPage {
  background: url('https://images.unsplash.com/photo-1512453979798-5ea266f8880c?w=1920&q=80') center/cover;
}

/* Results Page */
#resultsPage {
  background: url('https://images.unsplash.com/photo-1506461883276-594a12b11cf3?w=1920&q=80') center/cover;
  overflow-y: auto;
  align-items: flex-start;
  padding: 40px 20px;
}

.content {
  position: relative;
  z-index: 2;
  text-align: center;
  color: white;
  padding: 40px;
  max-width: 600px;
  animation: zoomIn 0.8s ease;
}

.page-title {
  font-size: 3.5em;
  margin-bottom: 20px;
  text-shadow: 3px 3px 6px rgba(0,0,0,0.7);
  letter-spacing: 2px;
}

.page-subtitle {
  font-size: 1.5em;
  margin-bottom: 40px;
  text-shadow: 2px 2px 4px rgba(0,0,0,0.7);
  opacity: 0.95;
}

.input-group {
  margin-bottom: 30px;
}

.input-label {
  font-size: 1.3em;
  margin-bottom: 15px;
  text-shadow: 2px 2px 4px rgba(0,0,0,0.7);
  font-weight: 600;
}

input[type="text"], input[type="number"], select {
  width: 100%;
  padding: 20px;
  font-size: 1.3em;
  border: 3px solid rgba(255,255,255,0.3);
  border-radius: 15px;
  background: rgba(255,255,255,0.95);
  color: #333;
  text-align: center;
  font-weight: 600;
  transition: all 0.3s ease;
}

input:focus, select:focus {
  outline: none;
  border-color: #fff;
  box-shadow: 0 0 30px rgba(255,255,255,0.5);
  transform: scale(1.02);
}

.btn {
  padding: 20px 60px;
  font-size: 1.4em;
  background: linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%);
  color: white;
  border: none;
  border-radius: 50px;
  cursor: pointer;
  font-weight: 700;
  box-shadow: 0 10px 30px rgba(255, 107, 107, 0.5);
  transition: all 0.3s ease;
  margin: 10px;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.btn:hover {
  transform: translateY(-5px) scale(1.05);
  box-shadow: 0 15px 40px rgba(255, 107, 107, 0.7);
}

.btn:active {
  transform: translateY(-2px) scale(1.02);
}

.btn-secondary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  box-shadow: 0 10px 30px rgba(102, 126, 234, 0.5);
}

.btn-secondary:hover {
  box-shadow: 0 15px 40px rgba(102, 126, 234, 0.7);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}

.mood-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
  margin-bottom: 30px;
}

.mood-card {
  background: rgba(255,255,255,0.95);
  padding: 30px;
  border-radius: 20px;
  cursor: pointer;
  transition: all 0.3s ease;
  border: 4px solid transparent;
  color: #333;
}

.mood-card:hover {
  transform: translateY(-10px);
  box-shadow: 0 20px 40px rgba(0,0,0,0.3);
  border-color: #ff6b6b;
}

.mood-card.selected {
  border-color: #ff6b6b;
  background: linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%);
  color: white;
}

.mood-icon {
  font-size: 4em;
  margin-bottom: 15px;
}

.mood-name {
  font-size: 1.5em;
  font-weight: 600;
}

.error-msg {
  background: rgba(211, 47, 47, 0.9);
  color: white;
  padding: 15px;
  border-radius: 10px;
  margin-top: 20px;
  font-weight: 600;
}

/* Results Styles */
.results-container {
  position: relative;
  z-index: 2;
  width: 100%;
  max-width: 1000px;
  margin: 0 auto;
}

.results-card {
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  padding: 30px;
  border-radius: 20px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.4);
  margin-bottom: 20px;
  animation: slideUp 0.6s ease;
}

.result-header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 30px;
  border-radius: 15px;
  margin-bottom: 30px;
  text-align: center;
}

.result-header h2 {
  font-size: 2.5em;
  margin-bottom: 10px;
}

.section {
  margin-bottom: 30px;
}

.section h3 {
  color: #667eea;
  font-size: 1.8em;
  margin-bottom: 20px;
  padding-bottom: 10px;
  border-bottom: 3px solid #667eea;
}

.item {
  background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
  padding: 20px;
  margin-bottom: 15px;
  border-radius: 12px;
  transition: all 0.3s ease;
  border-left: 5px solid #667eea;
}

.item:hover {
  transform: translateX(10px);
  box-shadow: 0 5px 20px rgba(0,0,0,0.15);
}

.item-name {
  font-size: 1.3em;
  font-weight: 700;
  color: #333;
  margin-bottom: 10px;
}

.item-details {
  color: #666;
  margin-bottom: 10px;
  font-size: 1.05em;
}

.item-price {
  display: inline-block;
  background: #4caf50;
  color: white;
  padding: 8px 16px;
  border-radius: 25px;
  font-weight: 700;
  margin-right: 10px;
  font-size: 1.05em;
}

.tier-budget { background: #2196f3; }
.tier-mid { background: #ff9800; }
.tier-luxury { background: #9c27b0; }

.map-link {
  display: inline-block;
  background: #667eea;
  color: white;
  padding: 8px 20px;
  border-radius: 25px;
  text-decoration: none;
  font-size: 1em;
  font-weight: 600;
  transition: all 0.3s ease;
}

.map-link:hover {
  background: #764ba2;
  transform: scale(1.1);
}

.cost-box {
  background: linear-gradient(135deg, #ffeaa7 0%, #fdcb6e 100%);
  padding: 25px;
  border-radius: 15px;
  font-size: 1.1em;
}

.cost-box pre {
  background: rgba(255,255,255,0.8);
  padding: 20px;
  border-radius: 10px;
  overflow-x: auto;
  font-size: 1.05em;
}

.back-btn {
  position: fixed;
  top: 30px;
  left: 30px;
  z-index: 10;
  background: rgba(255,255,255,0.9);
  color: #333;
  padding: 15px 30px;
  border-radius: 50px;
  border: none;
  cursor: pointer;
  font-weight: 700;
  font-size: 1.1em;
  box-shadow: 0 5px 20px rgba(0,0,0,0.3);
  transition: all 0.3s ease;
}

.back-btn:hover {
  background: white;
  transform: translateY(-3px);
  box-shadow: 0 8px 25px rgba(0,0,0,0.4);
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes zoomIn {
  from {
    opacity: 0;
    transform: scale(0.8);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 768px) {
  .page-title { font-size: 2.5em; }
  .page-subtitle { font-size: 1.2em; }
  .mood-grid { grid-template-columns: 1fr; }
  .btn { padding: 15px 40px; font-size: 1.2em; }
  .back-btn { top: 15px; left: 15px; padding: 10px 20px; font-size: 1em; }
}
</style>
</head>
<body>

<div id="welcomePage" class="page active">
  <div class="content">
    <h1 class="page-title">🇮🇳 Incredible India</h1>
    <p class="page-subtitle">Your Journey of a Lifetime Begins Here</p>
    <button class="btn" onclick="goToPage('regionPage')">
      ✈ Start Planning
    </button>
  </div>
</div>

<div id="regionPage" class="page">
  <div class="content">
    <h1 class="page-title">📍 Where to?</h1>
    <p class="page-subtitle">Choose your destination in India</p>
    <div class="input-group">
      <div class="input-label">City or Region</div>
      <input type="text" id="region" placeholder="e.g. Goa, Rishikesh, Jaipur">
    </div>
    <button class="btn" onclick="nextFromRegion()">Next →</button>
    <div id="regionError"></div>
  </div>
</div>

<div id="daysPage" class="page">
  <button class="back-btn" onclick="goToPage('regionPage')">← Back</button>
  <div class="content">
    <h1 class="page-title">📅 How long?</h1>
    <p class="page-subtitle">Number of days for your trip</p>
    <div class="input-group">
      <div class="input-label">Days</div>
      <input type="number" id="days" value="3" min="1" max="30">
    </div>
    <button class="btn" onclick="nextFromDays()">Next →</button>
    <div id="daysError"></div>
  </div>
</div>

<div id="moodPage" class="page">
  <button class="back-btn" onclick="goToPage('daysPage')">← Back</button>
  <div class="content">
    <h1 class="page-title">✨ What's your vibe?</h1>
    <p class="page-subtitle">Choose your travel mood</p>
    <div class="mood-grid">
      <div class="mood-card" onclick="selectMood('relaxed')">
        <div class="mood-icon">🏖</div>
        <div class="mood-name">Relaxed</div>
      </div>
      <div class="mood-card" onclick="selectMood('adventurous')">
        <div class="mood-icon">🏔</div>
        <div class="mood-name">Adventurous</div>
      </div>
      <div class="mood-card" onclick="selectMood('cultural')">
        <div class="mood-icon">🎭</div>
        <div class="mood-name">Cultural</div>
      </div>
      <div class="mood-card" onclick="selectMood('spiritual')">
        <div class="mood-icon">🕉</div>
        <div class="mood-name">Spiritual</div>
      </div>
    </div>
    <button class="btn" id="planTripBtn" onclick="planTrip()" disabled>
      🎉 Plan My Trip
    </button>
    <div id="moodError"></div>
  </div>
</div>

<div id="resultsPage" class="page">
  <button class="back-btn" onclick="goToPage('welcomePage')">← New Trip</button>
  <div class="results-container">
    <div class="results-card" id="resultsContent"></div>
  </div>
</div>

<script>
let tripData = {
  region: '',
  days: 3,
  mood: ''
};

function goToPage(pageId) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById(pageId).classList.add('active');
}

function nextFromRegion() {
  const region = document.getElementById('region').value.trim();
  const errorDiv = document.getElementById('regionError');

  if (!region) {
    errorDiv.innerHTML = '<div class="error-msg">⚠ Please enter a city or region</div>';
    return;
  }

  tripData.region = region;
  errorDiv.innerHTML = '';
  goToPage('daysPage');
}

function nextFromDays() {
  const days = Number(document.getElementById('days').value);
  const errorDiv = document.getElementById('daysError');

  if (days < 1 || days > 30) {
    errorDiv.innerHTML = '<div class="error-msg">⚠ Please enter between 1-30 days</div>';
    return;
  }

  tripData.days = days;
  errorDiv.innerHTML = '';
  goToPage('moodPage');
}

function selectMood(mood) {
  tripData.mood = mood;
  document.querySelectorAll('.mood-card').forEach(card => card.classList.remove('selected'));
  event.target.closest('.mood-card').classList.add('selected');
  document.getElementById('planTripBtn').disabled = false;
}

async function planTrip() {
  const btn = document.getElementById('planTripBtn');
  const errorDiv = document.getElementById('moodError');

  btn.disabled = true;
  btn.innerHTML = '⏳ Planning...';
  errorDiv.innerHTML = '';

  try {
    // API call to the Flask backend
    const res = await fetch('/plan_trip', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(tripData)
    });

    if (!res.ok) {
      const txt = await res.text().catch(() => null);
      errorDiv.innerHTML = `<div class="error-msg">❌ Server error: ${txt || res.status}</div>`;
      return;
    }

    const data = await res.json();
    displayResults(data);
    goToPage('resultsPage');

  } catch (e) {
    errorDiv.innerHTML = `<div class="error-msg">❌ Connection error: ${e.message}</div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '🎉 Plan My Trip';
  }
}

function displayResults(data) {
  let html = `
    <div class="result-header">
      <h2>🎉 ${data.region}</h2>
      <p style="font-size:1.3em">${data.mood.charAt(0).toUpperCase() + data.mood.slice(1)} Trip • ${data.days} Days</p>
      <p style="font-size:1em;margin-top:10px;opacity:0.9">📍 ${data.coordinates.lat}, ${data.coordinates.lon}</p>
    </div>
  `;

  if (data.stays && data.stays.length > 0) {
    html += '<div class="section"><h3>🏨 Accommodations</h3>';
    data.stays.forEach(s => {
      // Use s.tier to determine the class
      const tierClass = s.tier === 'Budget' ? 'tier-budget' : s.tier === 'Mid-range' ? 'tier-mid' : 'tier-luxury';
      html += `
        <div class="item">
          <div class="item-name">${s.name}</div>
          <div class="item-details">${s.address}</div>
          <span class="item-price ${tierClass}">${s.tier}</span>
          <span class="item-price">₹${s.price_inr}</span>
          <a href="${s.map_url}" target="_blank" class="map-link">📍 View Map</a>
        </div>
      `;
    });
    html += '</div>';
  }

  if (data.attractions && data.attractions.length > 0) {
    html += '<div class="section"><h3>🎯 Top Attractions</h3>';
    data.attractions.slice(0, 12).forEach(a => {
      html += `
        <div class="item">
          <div class="item-name">${a.name}</div>
          <div class="item-details">${a.address}</div>
          <a href="${a.map_url}" target="_blank" class="map-link">📍 View Map</a>
        </div>
      `;
    });
    html += '</div>';
  }

  if (data.restaurants && data.restaurants.length > 0) {
    html += '<div class="section"><h3>🍽 Recommended Restaurants</h3>';
    data.restaurants.slice(0, 8).forEach(r => {
      html += `
        <div class="item">
          <div class="item-name">${r.name}</div>
          <div class="item-details">${r.address}</div>
          <a href="${r.map_url}" target="_blank" class="map-link">📍 View Map</a>
        </div>
      `;
    });
    html += '</div>';
  }

  if (data.estimated_cost) {
    html += `
      <div class="section">
        <h3>💰 Estimated Cost</h3>
        <div class="cost-box">
          <pre>${JSON.stringify(data.estimated_cost, null, 2)}</pre>
        </div>
      </div>
    `;
  }

  document.getElementById('resultsContent').innerHTML = html;
}

document.getElementById('region').addEventListener('keypress', (e) => {
  if (e.key === 'Enter') nextFromRegion();
});

document.getElementById('days').addEventListener('keypress', (e) => {
  if (e.key === 'Enter') nextFromDays();
});
</script>

</body>
</html>
"""

# Route to serve the HTML file
@app.route("/")
def index():
    response = make_response(HTML_CONTENT)
    response.headers['Content-Type'] = 'text/html'
    return response

# API endpoint for trip planning
@app.route("/plan_trip", methods=["POST"])
def plan_trip():
    d = request.get_json()
    region, days, mood = d.get("region"), int(d.get("days",3)), d.get("mood","relaxed").lower()
    lat, lon = geoapify_geocode(region)
    if not lat: return jsonify({"error":"Could not geocode region"}),400
    
    # --- ATTRACTION LOGIC BASED ON MOOD ---
    if mood == "spiritual":
        attraction_categories = ["religion.place_of_worship"]
    else:
        attraction_categories = ["tourism.attraction","leisure.park"]

    attractions = geoapify_places(lat, lon, attraction_categories) or wikipedia_fallback(region)
    
    # --- CALLS THE CORRECTED MOOD_STAYS FUNCTION ---
    stays = mood_stays(lat, lon, mood)

    restaurants = geoapify_places(lat, lon, ["catering.restaurant"])
    
    # Calculate average cost for budget estimation
    # Use the price from the single default stay, or a safe default
    avg = 4000 
    if stays:
        if not stays[0]["name"].startswith("Default"):
             avg = int(sum(s["price_inr"] for s in stays)/len(stays))
        else:
             avg = stays[0]["price_inr"]
        
    cost = estimate_cost(days, avg)
    
    return jsonify({
        "region": region, "coordinates":{"lat":lat,"lon":lon},
        "mood": mood, "days": days,
        "stays": stays, 
        "attractions": attractions,
        "restaurants": restaurants,
        "estimated_cost": cost
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)