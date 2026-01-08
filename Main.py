"""
Line Follower Robot Controller
Bestuurt een robot die een lijn volgt en vooraf geprogrammeerde routes aflegt.
"""

from pyfirmata2 import Arduino, util
import time
import signal
import sys

from Config import ARDUINO_PORT, ROUTE_SEQUENCE
from MotorController import setup_motors, MotorController
from LineFollower import setup_sensors, LineFollower

# =============================================================================
# ARDUINO & SENSOR SETUP
# =============================================================================

def setup_arduino():
    """Initialiseer Arduino board en start de iterator."""
    board = Arduino(ARDUINO_PORT)
    iterator = util.Iterator(board)
    iterator.start()
    time.sleep(1)
    return board


# MAIN PROGRAM
def setup_graceful_exit(motor_controller, board):
    """Configureer netjes afsluiten bij Ctrl+C."""
    def signal_handler(sig, frame):
        print("\n\n⏹ Stoppen...")
        motor_controller.stop()
        board.exit()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)


def print_route_info(follower):
    """Toon route informatie bij opstarten."""
    print("=" * 60)
    print("🤖 LINE FOLLOWER ROBOT - START")
    print("=" * 60)
    print(f"Route: {follower.route_name}")
    print(f"Plan: {' → '.join(follower.route_plan)}")
    print(f"Totaal stappen: {len(follower.route_plan)}")
    print("=" * 60)
    print("Druk Ctrl+C om te stoppen\n")


def main():
    """Hoofdprogramma."""
    # Initialisatie
    board = setup_arduino()
    sensor_values = setup_sensors(board)
    motor_config = setup_motors(board)
    
    motor_controller = MotorController(motor_config)
    line_follower = LineFollower(motor_controller, sensor_values, ROUTE_SEQUENCE[0])
    
    setup_graceful_exit(motor_controller, board)
    print_route_info(line_follower)
    
    time.sleep(2)
    
    # Main loop
    try:
        while True:
            line_follower.update()
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        motor_controller.stop()
        board.exit()
        print("\n✓ Programma gestopt.")


if __name__ == "__main__":
    main()
