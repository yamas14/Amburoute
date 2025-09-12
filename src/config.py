MAPMYINDIA_CLIENT_ID = "96dHZVzsAutSOj_O6pI1sRqCXNJKHpQWjthbzO05LiTEjU8MOOQGAiKm1UtfWAZ-F4eyikYtmAlGBMv7_6jAbg=="
MAPMYINDIA_CLIENT_SECRET = "lrFxI-iSEg9Vf-ovv1WWHuvJfGUg4zQc__0yycT1jUt3LJ-7ESQJEJ3_sYkSb3uP7w6HMzQ4TlA01pGN1nDm98OTMXS4Dr0u"
MAPMYINDIA_REST_KEY = "2fc9a07cac1ce54c01a96a09bfb3ee6c"

# Mapbox Access Token (provided by user)
# NOTE: In production, prefer storing secrets in environment variables.
MAPBOX_ACCESS_TOKEN = "pk.eyJ1Ijoic2F0cmFqaXRoIiwiYSI6ImNtZjVpMTRlaTA1ZTIya3M4bjZjb2U5Z2cifQ.7GFkmIE8LP75DkaSzm8UVA"

# Optional: Real-time beds API configuration
# If REALTIME_BEDS_API_URL is set to a running FastAPI service with the bed endpoints,
# and HOSPITAL_NAME_TO_ID provides a mapping, the app will refresh available_beds before routing.
REALTIME_BEDS_API_URL = "http://localhost:8002"
HOSPITAL_NAME_TO_ID = {
    # NOTE: These IDs must match your backend database IDs exposed by /api/beds/current/{id}
    # The mapping below follows the order in bengaluru_hospitals.csv as a default.
    "Victoria Hospital": 1,
    "Bowring and Lady Curzon Hospital": 2,
    "Minto Eye Hospital": 3,
    "Jayadeva Institute of Cardiovascular Sciences and Research": 4,
    "NIMHANS": 5,
    "Kidwai Memorial Institute of Oncology": 6,
    "St. Martha’s Hospital": 7,
    "Rajiv Gandhi Institute of Chest Diseases": 8,
    "Indira Gandhi Institute of Child Health": 9,
    "BMCRI": 10,
    "Bangalore Baptist Hospital": 11,
    "HOSMAT Hospital": 12,
    "Aster RV Hospital": 13,
    "Narayana Multispeciality Hospital": 14,
    "Fortis Hospital": 15,
    "Manipal Hospital": 16,
    "Columbia Asia Hospital": 17,
    "Sagar Hospital": 18,
    "The Bangalore Hospital": 19,
    "K C General Hospital": 20,
}

# When True and REALTIME_BEDS_API_URL is set, the app will attempt to
# auto-discover hospital IDs by probing /api/beds/current/{id} and matching
# names to those loaded from CSV. Any IDs found will be merged into the
# HOSPITAL_NAME_TO_ID mapping at runtime (without overwriting existing entries).
AUTO_DISCOVER_HOSPITAL_IDS = True