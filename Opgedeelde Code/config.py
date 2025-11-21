from pyfirmata2 import Arduino, util
import time
import signal
import sys

# Configuratie
PORT = 'COM3'          # Pas aan indien nodig

# Aparte basis-snelheden per motor
BASE_SPEED_LEFT = 0.21     # linker motor basis
BASE_SPEED_RIGHT = 0.25   # rechter motor basis

SHARP_TURN = 0.8
SMOOTH_TURN = 0.6
THRESHOLD = 0.5        # drempel voor zwart/wit
CROSS_COOLDOWN = 0.5   # s na bocht geen nieuwe kruispuntbeslissing (verlaagd voor snellere detectie)
ROUTES = {
    "depot-achtbaan": {"plan": ["straight", "straight", "straight", "straight", "left", "straight"], "loc": "Trein depot"},
}
ROUTE_VOLGORDE = [
    "depot-achtbaan"
]

# Pin checker
def require_pin(pin, name):
    if pin is None:
        raise RuntimeError(f"Pin '{name}' kon niet worden geïnitialiseerd.")
    return pin

# Arduino setup
board = Arduino(PORT)
it = util.Iterator(board)
it.start()
time.sleep(1)
