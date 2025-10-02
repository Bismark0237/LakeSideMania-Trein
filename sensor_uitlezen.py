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

# Gebruik de actuele waarden uit sensorwaarden
if __name__ == "__main__":
    try:
        while True:
            print(f"Ruwe sensorwaarden: {sensorwaarden}")  # Print duidelijk de actuele waarden
            time.sleep(1)
    except KeyboardInterrupt:
        print("Gestopt door gebruiker.")
