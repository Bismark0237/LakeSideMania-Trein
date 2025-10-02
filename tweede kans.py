from pyfirmata2 import Arduino, util
import time

board = Arduino('COM4')

# Maak een lijst met je analoge sensoren
sensor_L1 = board.get_pin('a:1:i')  # Analog pin voor ver links
sensor_L2 = board.get_pin('a:2:i')  # Analog pin voor links
sensor_M = board.get_pin('a:3:i')  # Analog pin voor midden
sensor_R2 = board.get_pin('a:4:i')  # Analog pin voor rechts
sensor_R1 = board.get_pin('a:5:i')  # Analog pin voor ver rechts

# Maak een lijst van alle sensoren
sensoren = [sensor_L1, sensor_L2, sensor_M, sensor_R2, sensor_R1]
# Lijst om actuele sensorwaarden op te slaan
sensorwaarden = [None] * len(sensoren)

# Callback-functie voor elke sensor
def maak_callback(index):
    def callback_waarde(value):
        sensorwaarden[index] = value
    return callback_waarde

# Start de iterator en koppel de callbacks
it = util.Iterator(board)
it.start()
for i, sensor in enumerate(sensoren):
    sensor.register_callback(maak_callback(i))
    sensor.enable_reporting()

time.sleep(1)  # Wacht even zodat de eerste waarden binnenkomen

# -------------------------------
# Motorfuncties
# -------------------------------
motor_left = board.get_pin('d:11:p')
motor_right = board.get_pin('d:3:p')

def set_motor_speeds(left_speed, right_speed):
    motor_left.write(left_speed)
    motor_right.write(right_speed)

def vooruit(snelheid=0.8):
    set_motor_speeds(snelheid, snelheid)

def links(snelheid=0.6):
    set_motor_speeds(0, snelheid)

def rechts(snelheid=0.6):
    set_motor_speeds(snelheid, 0)

def stop():
    set_motor_speeds(0, 0)

# -------------------------------
# Lijnvolg-logica
# -------------------------------
def bepaal_actie(drempel=0.5):
    # Wacht tot alle sensoren een waarde hebben
    if None in sensorwaarden:
        return  # Nog niet alle waarden beschikbaar

    bits = [1 if v > drempel else 0 for v in sensorwaarden]
    print(f"Sensorwaarden (bits): {bits}")

    # Beslis actie op basis van sensorbits
    if bits == [0,0,1,0,0]:
        actie = "Vooruit"
        vooruit()
    elif bits[0] == 1:
        actie = "Links"
        links()
    elif bits[-1] == 1:
        actie = "Rechts"
        rechts()
    elif sum(bits) == 0:
        actie = "Stop (lijn kwijt)"
        stop()
    else:
        actie = "Corrigeren"
        if 1 in bits[:2]:
            links()
        else:
            rechts()
    
    print(f"Actie: {actie}\n")

# -------------------------------
# Main-loop
# -------------------------------
if __name__ == "_main_":
    try:
        while True:
            print(f"Ruwe sensorwaarden: {sensorwaarden}")  # Print duidelijk de actuele waarden
            bepaal_actie()
            time.sleep(0.1)  # Interval voor snelle reactie
    except KeyboardInterrupt:
        stop()
        print("Gestopt door gebruiker.")