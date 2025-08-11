import machine
import os
import utime
import binascii
import _thread
import sys

from collections import deque
from modem import Modem


# using pin defined
pwr_en = 14  # pin to control the power of the module
uart_port = 0
uart_baute = 115200


buffer = deque([], 1000)

print(os.uname())


modem = Modem(port=uart_port, baute=uart_baute)


class Listener:

    def run(self):
        print("\n--- STARTING EVENT LISTENER ---")

        while True:
            response = modem.uart_read()
            print(f"Uart message: {response}")
            if response:
                buffer.append(response)
            utime.sleep(1)
        
class Handler:
    
    def run(self):
        while True:
            if len(buffer) == 0:
                continue
                utime.sleep(0.1)
            response = buffer.popleft()
            print(f"[INFO] Response received: {response}")
            modem.handle_uart_message(response)


# --------------------------------------------  MAIN  ----------------------------------------------
def main():
    try:
        modem.init_device()
        listener = Listener()
        handler = Handler()
        # Thread #2
        _thread.start_new_thread(listener.run, ())

        # Main thread
        handler.run()        
    except Exception as e:
        print(e)
        raise e
    finally:
        # byc moze jakies czyszczenie urzadzenia, jezeli jest potrzebne
        pass

main()

