from pyfirmata2 import Arduino, util
import pyfirmata2
import time
import signal
import sys

# =============================================================================
# CONFIGURATIE
# =============================================================================

# Arduino verbinding
ARDUINO_PORT = 'COM4'

def initialize_pin(pin, name):
    """Controleer of een pin correct is geïnitialiseerd."""
    if pin is None:
        raise RuntimeError(f"Pin '{name}' kon niet worden geïnitialiseerd.")
    return pin

def setup_arduino():
    """Initialiseer de Arduino en start de iterator."""
    board = Arduino(ARDUINO_PORT)
    it = util.Iterator(board)
    it.start()
    time.sleep(1)  # Wacht even voor stabiliteit
    return board

def setup_sensors(board):
    """Configureer de 5 lijnsensoren met callbacks."""
    sensor_values = [0.5] * 5  # Neutrale startwaarden
    
    def create_callback(index):
        """Factory functie voor sensor callbacks."""
        def callback(data):
            if data is not None:
                sensor_values[index] = data
        return callback
    
    # Initialiseer analoge sensoren A1 t/m A5
    sensor_pins = [board.get_pin(f'a:{i}:i') for i in range(1, 6)]
    
    for i, pin in enumerate(sensor_pins):
        pin = initialize_pin(pin, f"Sensor A{i+1}")
        pin.register_callback(create_callback(i))
        pin.enable_reporting()
    
    time.sleep(1)
    return sensor_values

def setup_display(board):
    """Configureer de 7-segment display pinnen."""
    segments = {}
    # Voorbeeld pinnen voor segmenten a-g (pas aan naar jouw setup)
    segment_pins = {'a': 2, 'b': 4, 'c': 7, 'd': 8, 'e': 9, 'f': 10}  # g op A0 als digitale pin 14
    for seg, pin in segment_pins.items():
        segments[seg] = board.get_pin(f'd:{pin}:o')
    return segments


def display_number(segments, number):
    """Toon een cijfer op de 7-segment display."""
    segment_map = {
        0: 'abcdef',
        1: 'bc',
        2: 'abdeg',
        3: 'abgcd',
        4: 'fgbc',
        5: 'afgcd',
        6: 'afgcde',
        7: 'abc',
        8: 'abcdefg',
        9: 'abcfg',
    }

    # Zet alle segmenten uit
    for seg in segments.values():
        seg.write(0)

    # Zet de juiste segmenten aan voor het cijfer
    if number in segment_map:
        for seg in segment_map[number]:
            if seg in segments:
                segments[seg].write(1)


def test_display(segments):
    """Test de 7-segment display door alle segmenten aan te zetten."""
    print("Test: Alle segmenten aanzetten...")
    # Zet alle segmenten aan
    for seg in segments.values():
        seg.write(1)
    time.sleep(2)

    print("Test: Alle segmenten uitzetten...")
    # Zet alle segmenten uit
    for seg in segments.values():
        seg.write(0)
    time.sleep(1)

    print("Test: Elk segment individueel aanzetten...")
    # Test elk segment individueel
    for name, seg in segments.items():
        print(f"Segment {name} aan...")
        seg.write(1)
        time.sleep(0.5)
        seg.write(0)
        time.sleep(0.2)

    print("Test: Cijfers 0-9 tonen...")
    for num in range(10):
        display_number(segments, num)
        time.sleep(0.5)

    # Zet alle segmenten uit na de test
    for seg in segments.values():
        seg.write(0)
    print("Test voltooid.")




# Hoofdprogramma
if __name__ == '__main__':
    board = setup_arduino()
    sensor_values = setup_sensors(board)
    segments = setup_display(board)

    # Test de 7-segment display
    test_display(segments)

    board.exit()

