# =============================================================================
# CONFIGURATIE
# =============================================================================

# Arduino verbinding
ARDUINO_PORT = 'COM4'

# Motor kalibratie (aangepast voor individuele motorverschillen)
BASE_SPEED_LEFT = 0.4
BASE_SPEED_RIGHT = 0.4

# Sensor drempelwaarde voor zwart/wit detectie
SENSOR_THRESHOLD = 0.5

# Timing constanten
CROSS_COOLDOWN = 0.3  # Verkort voor betere kruispuntdetectie
TURN_COOLDOWN = 2   # Langere cooldown na bochten voor stabilisatie
SPIN_TIMEOUT = 2.5    # Maximale tijd voor draai-operatie
POST_TURN_DELAY = 1  # Vertraging na turn voor stabiele detectie

# Motor snelheid constanten
TURN_SPEED_FACTOR = 0.45  # Factor voor draaisnelheid

# Route definities
ROUTES = {
    "depot-arcade": {
        "plan": ["right", "left", "stop"],
        "destination": "Arcade"
    },
    "depot-wildwaterbaan": {
        "plan": ["right", "straight", "straight", "left", "left", "stop"],
        "destination": "Wildwaterbaan"
    },
    "depot-achtbaan": {
        "plan": ["straight", "straight", "straight", "left", "stop"],
        "destination": "Achtbaan"
    },
    "depot-reuzenrad": {
        "plan": ["straight", "straight", "left", "stop"],
        "destination": "Reuzenrad"
    }
}

ROUTE_SEQUENCE = ["depot-achtbaan"]  # Kies welke route te volgen
