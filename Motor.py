from pyfirmata2 import Arduino, util
import time
import logging
import signal

board = Arduino('COM3')  

motor_links = board.get_pin('d:11:p')  # PWM pin for left motor
richting_links = board.get_pin('d:13:o')  # Direction pin for left motor
brake_links = board.get_pin('d:8:o')  # Brake pin for left motor

motor_rechts = board.get_pin('d:3:p')  # PWM pin for right motor
richting_rechts = board.get_pin('d:12:o')  # Direction pin for right motor
brake_rechts = board.get_pin('d:9:o')  # Brake pin for right motor

time.sleep(1)  # Wacht even zodat de pinnen klaar zijn

# motor_links.write(0)
# motor_rechts.write(0)
# richting_links.write(0)  # 0 voor vooruit, 1 voor achteruit
# richting_rechts.write(0)  # 0 voor vooruit, 1 voor achteruit
# brake_links.write(0)  # 1 om te remmen, 0 om te rijden
# brake_rechts.write(0)  # 1 om te remmen, 0 om te rijden

# def signal_handler(sig, frame):
#     print('Keyboard interrupt ontvangen. Motors stoppen...')
#     motor_links.write(0)
#     motor_rechts.write(0)
#     board.exit()
#     exit(0)

# signal.signal(signal.SIGINT, signal_handler)

class MotorController:
    def __init__(self, motor_links, motor_rechts, richting_links, richting_rechts, brake_links, brake_rechts):
        self.motor_links = motor_links
        self.motor_rechts = motor_rechts
        self.richting_links = richting_links
        self.richting_rechts = richting_rechts
        self.brake_links = brake_links
        self.brake_rechts = brake_rechts


    def set_speeds(self, snelheid_links, snelheid_rechts):
        try:
            snelheid_links = max(0, min(1, snelheid_links))  # Beperk tot 0-1
            snelheid_rechts = max(0, min(1, snelheid_rechts))  # Beperk tot 0-1
       
            # Set PWM speeds
            self.motor_links.write(snelheid_links)
            self.motor_rechts.write(snelheid_rechts)
            logging.info(f"Motorsnelheden ingesteld: Links={snelheid_links}, Rechts={snelheid_rechts}")
            time.sleep(0.1)  # Korte pauze om de motoren tijd te geven om te reageren
        except Exception as e:
            print(f"Fout bij het instellen van motorsnelheden: {e}")
            logging.error(f"Fout bij het instellen van motorsnelheden: {e}")
            try:
                self.motor_links.write(0)
                self.motor_rechts.write(0)
                logging.info("Motors uitgeschakeld vanwege fout.")
            except Exception as e2:
                print(f"Fout bij het uitschakelen van motors: {e2}")
                pass

# Instantiate the MotorController
motor_controller = MotorController(motor_links, motor_rechts, richting_links, richting_rechts, brake_links, brake_rechts)

# Test loop to set speeds to 0.5
if __name__ == "__main__":
    try:
        print("Setting motor speeds to 0.5 for testing...")
        motor_controller.set_speeds(0.3, 0.3)
        time.sleep(5)  # Run for 5 seconds
        motor_controller.set_speeds(0, 0)  # Stop motors
        print("Test completed.")
    except KeyboardInterrupt:
        motor_controller.set_speeds(0, 0)
        print("Test interrupted.")
