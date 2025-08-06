import machine
import os
import utime
import binascii
import _thread

 #uart lock added so that detecting calls and sms functions could work at the same time - maybe there's an easier way to do this



# using pin defined
led_pin = 25  # onboard led
pwr_en = 14  # pin to control the power of the module
uart_port = 0
uart_baute = 115200

APN = "internet" #defined for the mobile operator

reading = 0
temperature = 0

# uart setting
uart = machine.UART(uart_port, uart_baute)

uart_lock = _thread.allocate_lock()

print(os.uname())

class Modem:
    
    def __init__(self, port, baute):
        self.uart = machine.UART(port, baute)
        self.uart_lock = _thread.allocate_lock()

    def hang_up(self):
        """
        Hangs up the current call.
        """
        # with uart_lock:
              # obecny watek dosal wylacznosc na wykonanie ponizszej lini
              # uart.write...
        
        with self.uart_lock:
            self.uart.write(b"ATH\r\n")
            
    def get_contact_range(self):
        """
        Returns available contact index range stored on the SIM card
        
        :return: contact index range
    
        """
        with self.uart_lock:
            self.uart.write(b'AT+CPBR=?\r\n') 
            utime.sleep(0.5)
            resp = self.uart.read().decode('ignore')
            return resp

    def read_sms_by_index(self, sms_index):
        """
        Reads SMS from a specific memory index
        
        :param sms_index: index of the SMS to read
        :return: SMS message as a string
        """
        with self.uart_lock:
            self.uart.write(b"AT+CMGF=1\r\n")  # Set to text mode
            utime.sleep(0.2)
            
            self.uart.write(f"AT+CMGR={sms_index}\r\n".encode())
            utime.sleep(0.5)
            return self.uart.read().decode('ignore')f
        
    def read_contact(self, i):
        """
        Reads a single contact entry (name, number, ...) from the SIM card phonebook
        
        :param i: index of contact to read
        :return: contact entry as a string
        """
        with self.uart_lock:
            self.uart.write(f'AT+CPBR={i}\r\n'.encode())
            utime.sleep(0.3)
            entry = self.uart.read().decode('ignore')
            return entry
        
            
    def delete_sms(self, sms_index):
        """
        Deletes message from the SIM card

        :param sms_index: index of the SMS to delete
        """
        with self.uart_lock:
            self.uart.write(f"AT+CMGD={sms_index}\r\n".encode())
            utime.sleep(0.5)
            
            if self.uart.any():
                response = self.uart.read().decode("ignore")
                print(f"[DEBUG] Delete SMS response: {response}")
                if "OK" in response:
                    print(f"[INFO] SMS at index {sms_index} deleted.")
                else:
                    print(f"[WARNING] Failed to delete SMS at index {sms_index}")
            else:
                print(f"[WARNING] No response after attempting to delete SMS at index {sms_index}")
            
    def send_sms_text(self, number, message):
        """
        Sends SMS message to the given phone number
        
        :param number: phone number
        :param message: text message to send
        """
        with self.uart_lock:
            send_at("AT+CMGF=1", "OK")  # tryb tekstowy
            utime.sleep(0.5)

            self.uart.write(f'AT+CMGS="{number}"\r\n'.encode())
            utime.sleep(1)

            self.uart.write(message.encode() + b"\x1A")  # CTRL+Z ends the SMS input and sends it
            
    def uart_read(self):
        """
        Reads and decodes uart response

        :return: decoded response string or empty string
        """
        with self.uart_lock:
            if self.uart.any():
                return self.uart.read().decode('ignore')
            else:
                return ""
    
            
modem = Modem(port=uart_port, baute=uart_baute)

# LED indicator on Raspberry Pi Pico
led_onboard = machine.Pin(led_pin, machine.Pin.OUT)

# MQTT Server info
mqtt_host = '47.89.22.46'
mqtt_port = '1883'

mqtt_topic1 = 'testtopic'
mqtt_topic2 = 'testtopic/led'
mqtt_topic3 = 'testtopic/temp'
mqtt_topic4 = 'testtopic/adc'
mqtt_topic5 = 'testtopic/tempwarning'
mqtt_topic6 = 'testtopic/warning'
mqtt_topic7 = 'testtopic/gpsinfo'

mqtt_msg = 'on'


def led_blink():
    led_onboard.value(1)
    utime.sleep(1)
    led_onboard.value(0)
    utime.sleep(1)
    led_onboard.value(1)
    utime.sleep(1)
    led_onboard.value(0)

def wait_resp_info(timeout=2000):
    prvmills = utime.ticks_ms()
    info = b""
    while (utime.ticks_ms()-prvmills) < timeout:
        if uart.any():
            info = b"".join([info, uart.read(1)])
    print(info.decode())
    return info

# power on/off the module
def power_on_off():
    pwr_key = machine.Pin(pwr_en, machine.Pin.OUT)
    pwr_key.value(1)
    utime.sleep(2)
    pwr_key.value(0)

# Send AT command
def send_at(cmd, back, timeout=2000):
    rec_buff = b''
    with uart_lock:
        uart.write((cmd+'\r\n').encode())
        prvmills = utime.ticks_ms()
        while (utime.ticks_ms()-prvmills) < timeout:
            if uart.any():
                rec_buff = b"".join([rec_buff, uart.read(1)])
    if rec_buff != b'':
        if back not in rec_buff.decode():
            print(cmd + ' back:\t' + rec_buff.decode())
            return 0
        else:
            print(rec_buff.decode())
            return 1
    else:
        print(cmd + ' no response')

        

# Module startup detection
def check_start():
    for i in range(3):  
        with uart_lock:
            uart.write(b'ATE1\r\n')
        utime.sleep(2)
        with uart_lock:
            uart.write(b'AT\r\n')
        rec = wait_resp_info()
        if "OK" in rec.decode():
            print("[OK] SIM868 is ready")
            return True
        else:
            power_on_off()
            print("[INFO] Restarting SIM868...")
            utime.sleep(8)
    print("[ERROR] SIM868 failed to start.")
    return False


def check_gsm():
    print("\n--- GSM & GPRS MODULE TEST ---")

    print("\n[INFO] Resetting GSM module...")
    send_at("AT+CFUN=1,1", "OK")  # Full modem reset - for some reason if you don't reset it every time, it doesn't work
    print("[INFO] Waiting for module to reboot...")
    utime.sleep(10)

    commands = [
        ("AT", "OK"),
        ("ATE1", "OK"),  # Enable echo
        ("AT+CPIN?", "READY"),  # SIM card ready?
        ("AT+CSQ", "OK"),  # Signal quality
        ("AT+COPS?", "OK"),  # Operator
        ("AT+CREG?", "0,1"),  # GSM network registration
        ("AT+CGREG?", "0,1"),  # GPRS network registration
        ("AT+CGATT?", "OK"),  # GPRS attach status
        ("AT+CGATT=1", "OK"),  # Force attach to GPRS
        (f'AT+CSTT="{APN}","",""', "OK"),  # Set APN
        ("AT+CSTT?", "OK"),  # Check APN
        ("AT+CIICR", "OK"),  # Bring up wireless connection
        ("AT+CIFSR", "")  # Get local IP address
    ]

    for cmd, expected_response in commands:
        print(f"\nSending: {cmd}")
        success = send_at(cmd, expected_response)
        if success:
            print("[OK]")
        else:
            print(f"[ERROR] Command failed: {cmd}")
            return False  

    print("\n--- GSM & GPRS MODULE READY ---")
    return True

def monitor_incoming_calls():
    print("\n--- STARTING INCOMING CALL MONITOR ---")

    send_at("AT+CLIP=1", "OK")  # Enable caller ID

    call_active = False
    ring_start_time = 0
    caller_number = ""
    caller_name = ""

    while True:
        utime.sleep(0.5)
        response = modem.uart_read()
        
        print(f"Incomming call: read UART: {response}")
        if "RING" in response:
            if not call_active:
                print("\n[INFO] Incoming call detected.")
                call_active = True
                ring_start_time = utime.ticks_ms()

        # Checks if the number is saved or not
        if "+CLIP:" in response: # If enabled +CLIP notification
            try:
                clip_line = ""
                for line in response.splitlines():
                    if "+CLIP:" in line:
                        clip_line = line
                        break
                parts = clip_line.split('"')
                caller_number = parts[1] if len(parts) > 1 else "Unknown"
                caller_name = parts[5] if len(parts) > 3 and parts[5] else "Unknown"

                print(f"[CALLER] Number: {caller_number}, Name: {caller_name}")

                if is_number_in_sim(caller_number):
                    print("[INFO] Caller number is in SIM contacts. Hanging up.")
                    modem.hang_up()
                    
                    # Opens the gate
                    
                    call_active = False
                    ring_start_time = 0
                    caller_number = ""
                    caller_name = ""
                    continue  
                else:
                    print("[WARNING] Unknown number. Hanging up.")
                    modem.hang_up()
                    
                    call_active = False
                    ring_start_time = 0
                    caller_number = ""
                    caller_name = ""
                    continue  

            except Exception as e:
                print("[ERROR] Failed to parse CLIP:", e)

        if call_active:
            print("RINGING...")
            if utime.ticks_diff(utime.ticks_ms(), ring_start_time) > 5:
                print("[INFO] Hanging up the call.")
                modem.hang_up()
                
                call_active = False
                ring_start_time = 0
                caller_number = ""
                caller_name = ""
        else:
            utime.sleep(3)
            print("[CHECK] No call... checking again.")        

def add_contact(number):
    if is_number_in_sim(number):
        print(f"[INFO] Number already saved.")
    else:
        name = "user"

        number_type = 145 if number.startswith('+') else 129
    
        command = f'AT+CPBW=1,"{number}",{number_type},"{name}"'
        print(f"\nSending: {command}")
        if send_at(command, "OK"):
            print(f"[OK] Contact '{name}' with number '{number}' saved to SIM.")
        else:
            print(f"[ERROR] Failed to save contact.")
        
def delete_contact(number_to_delete):

    response = modem.get_contact_range()
    
    try:
        start = response.index('(') + 1
        end = response.index(')')
        index_range = response[start:end]
        min_idx, max_idx = [int(x) for x in index_range.split('-')]

    except:
        print("[ERROR] Failed to parse index range")
        return
    
    for i in range(min_idx, max_idx + 1):
        entry = modem.read_contact(i)
        if number_to_delete in entry:
            print(f"[INFO] Found number at index {i}, deleting...")
            uart.write(f'AT+CPBW={i}\r\n'.encode())  # delete
            utime.sleep(0.2)
            print(f"[OK] Contact with number {number_to_delete} deleted.")
            return

    print(f"[INFO] Number {number_to_delete} not found in SIM contacts.")

def is_number_in_sim(contact_number):
    resp = modem.get_contact_range()

    try:
        start = resp.index('(') + 1
        end = resp.index(')')
        index_range = resp[start:end]
        min_idx, max_idx = [int(x) for x in index_range.split('-')]

        for i in range(min_idx, max_idx + 1):
            entry = modem.read_contact(i)

            if "+CPBR:" in entry: # If number in phonebook
                try:
                    parts = entry.split(',')
                    sim_number = parts[1].strip().strip('"')
                    name = parts[3].strip().strip('"')

                    if sim_number == contact_number:
                        return sim_number
                except:
                    pass
        return None

    except Exception as e:
        print("[ERROR] Could not read SIM contacts:", e)
        return None
    
def get_name_from_sim(number):
    
    send_at("AT+CPBR=1,100", "OK")  # Reads phonebook
    utime.sleep(0.5)

    response = modem.uart_read()
    
    for line in response.splitlines():
        if number in line:
            parts = line.split(",")
            if len(parts) >= 4:
                name = parts[3].strip().strip('"')
                return name
    return "Unknown"
        
def check_for_call():
    if check_start():
        if check_gsm():
            monitor_incoming_calls()
        else:
            print("[ERROR] GSM setup failed. Incoming call monitor not started.")
    else:
        print("[ERROR] SIM module failed to start.")
   


def read_sms():
    send_at("AT+CMGF=1", "OK")  # Set SMS system into text mode
    utime.sleep(0.3)

    while True:
        utime.sleep(1)
        response = modem.uart_read()
        
        print(f"SMS uart: {response}")
        
        if "+CMTI:" in response: # Indicates that new message has been received
            try:
                print("\n[INFO] New SMS received.")
                
                # Gets index of message
                for line in response.splitlines():
                    if "+CMTI:" in line:
                        parts = line.split(",")
                        sms_index = int(parts[1].strip())
                        break
                    
                sms_resp = modem.read_sms_by_index(sms_index)
                
                print(f"[INFO] Text of SMS: {sms_resp}")

                lines = sms_resp.splitlines()
                header = lines[5] if len(lines) > 0 else "" # number, name, date, ...
                text = "\n".join(lines[6:]).strip()
                print(f"[DEBUG] SMS Header: {header}")

                try:
                    header_parts = header.split('"')
                    sender_number = header_parts[3] if len(header_parts) > 1 else "Unknown"
                    sender_name = header_parts[5] if len(header_parts) > 3 else "Unknown"
                except:
                    print("[ERROR] Parsing sender info failed")
                
                print(f"[SMS] From: {sender_number} ({sender_name})")
                print(f"[SMS] Message: {text}")
                
                # Max 25 messages
                if sms_index > 24:
                    resp = send_at("AT+CMGD=1,4", "OK")
                    if resp and "OK" in resp:
                        print("[INFO] All messages deleted.")
                    else:
                        print("[WARNING] Failed to delete all messages.")
                else:
                    print(f"[INFO] Deleting SMS at index: {sms_index}")
                    modem.delete_sms(sms_index)
                
                if is_number_GK(sender_number):
                    print(f"[INFO] Sender number is GK.")
                    message = sms_command(text)
                    if message:
                        send_sms(sender_number, message)
                    
                else:
                    print(f"[INFO] Not GK number.")
                
            except Exception as e:
                print("[ERROR] Failed to parse SMS:", e)
        else:
            utime.sleep(2)
           
def sms_command(text): 

    if text.startswith("+"):
        number = text[1:].strip().split()[0]
        add_contact(number)
        print(f"[OK] Added number: {number}")
        message = f"Number {number} added to SIM card."
        return message
        
    elif text.startswith("-"):
        number = text[1:].strip().split()[0]
        delete_contact(number)
        print(f"[OK] Deleted number: {number}")
        message = f"Number {number} deleted from SIM card."
        return message
        
    elif text.startswith("?"):
        number = text[1:].strip().split()[0]
        is_number_in_sim(number)
        if is_number_in_sim(number):
            print(f"[INFO] Number {number} is in SIM card.")
            message = f"Number {number} is in SIM card."
            return message
        else:
            print(f"[INFO] Number {number} not found.")
            message = f"Number {number} not found."
            return message

    elif text.startswith("W trakcie") or text.startswith("Masz"):
        return
    
    else:
        print("[ERROR] Unknown command.")
        message = f"Unknown command. Use +, - or ?."
        return message
    
GK_numbers = [
    "+48503815525"
]

def is_number_GK(number):
    return number in GK_numbers

def send_sms(number, message):
    print("\n--- SEND SMS ---")
    
    print(f"[INFO] Sending SMS to {number}...")

    try:
        modem.send_sms_text(number, message)

        print("[INFO] Message sent. Waiting for confirmation...")

        # Waits up to 5 seconds for a modem response
        # Checks uart every 0.5s and prints the first available response
        for _ in range(10):
            utime.sleep(0.5)
            with uart_lock:
                if uart.any():
                    response = uart.read().decode('ignore')
                    print("[MODEM RESPONSE]:\n", response)
                    break
        else:
            print("[WARNING] No response from modem.")
    except Exception as e:
        print("[ERROR] Exception while sending SMS:", e)



# --------------------------------------------  MAIN  ----------------------------------------------

# Thread #2: monitoring SMS
_thread.start_new_thread(read_sms, ())

# Run call monitor in main thread
check_for_call()

#send_at("AT+CPMS?", "OK")
#send_at("AT+CMGD=1,4", "OK")
#modem.delete_sms(4)
#send_at("AT+CMGF=1", "OK")
#send_at('AT+CMGL="ALL"', "OK")
