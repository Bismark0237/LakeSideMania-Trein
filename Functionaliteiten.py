from pyfirmata2 import Arduino, util
import time

board = Arduino('COM4')  

motor_left = board.get_pin('d:11:p')  # PWM pin for left motor
motor_right = board.get_pin('d:3:p')  # PWM pin for right motor

sensor_L1 = board.get_pin('a:1:i')  # Analog pin voor ver links
sensor_L2 = board.get_pin('a:2:i')  # Analog pin voor links
sensor_M = board.get_pin('a:3:i')  # Analog pin voor midden
sensor_R2 = board.get_pin('a:4:i')  # Analog pin voor rechts
sensor_R1 = board.get_pin('a:5:i')  # Analog pin voor ver rechts


def set_motor_speeds(left_speed, right_speed):
    motor_left.write(left_speed)
    motor_right.write(right_speed)

# Sensor uitlezen en actie bepalen
sensoren = [sensor_L1, sensor_L2, sensor_M, sensor_R2, sensor_R1]

# Start de iterator voor analoge uitlezing
it = util.Iterator(board)
it.start()
for sensor in sensoren:
    sensor.enable_reporting()

# Wacht even zodat de eerste sensorwaarden binnenkomen
time.sleep(1)

def lees_sensors():
    waarden = [sensor.read() for sensor in sensoren]
    return waarden

def bepaal_actie(waarden, drempel=0.5):
    # Print de ruwe sensorwaarden voor debuggen
    print(f"Ruwe sensorwaarden: {waarden}")
    # Zet sensorwaarden om naar 0 of 1
    bits = [1 if v is not None and v > drempel else 0 for v in waarden]
    print(f"Sensorwaarden (bits): {bits}")
    # Eenvoudige logica voor lijnvolgen
    if bits == [0,0,1,0,0]:
        actie = "Vooruit"
    elif bits[0] == 1:
        actie = "Links"
    elif bits[-1] == 1:
        actie = "Rechts"
    elif sum(bits) == 0:
        actie = "Stop (lijn kwijt)"
    else:
        actie = "Corrigeren"
    print(f"Actie: {actie}")
    return actie

# Voorbeeld loop
if __name__ == "__main__":
    try:
        while True:
            waarden = lees_sensors()
            bepaal_actie(waarden)
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("Gestopt door gebruiker.")



# Functies voor motorbesturing
# def vooruit(snelheid=1.0):
#     set_motor_speeds(snelheid, snelheid)

# def links(snelheid=1.0):
#     set_motor_speeds(0, snelheid)

# def rechts(snelheid=1.0):
#     set_motor_speeds(snelheid, 0)

# def stop():
#     set_motor_speeds(0, 0)