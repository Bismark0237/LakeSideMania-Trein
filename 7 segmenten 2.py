from pyfirmata2 import Arduino
from time import sleep

board = Arduino("COM4")  # Adjust the port as necessary
led_left = board.get_pin('d:5:o')  # Digital pin 8 as output
led_right = board.get_pin('d:6:o')    # Digital pin 9 as

def set_status(status):
    if status == "normal":
        led_left.write(1)
        led_right.write(0)
    elif status == "obstacle":
        led_left.write(0)
        led_right.write(1)
    else:
        led_left.write(0)
        led_right.write(0)

# Test the status lights
set_status("normal")
sleep(2)
set_status("obstacle")
sleep(2)
