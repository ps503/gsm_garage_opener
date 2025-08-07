import machine
import os
import utime
import binascii
import _thread
import sys

from collections import deque


# using pin defined
pwr_en = 14  # pin to control the power of the module
uart_port = 0
uart_baute = 115200

APN = "internet" #defined for the mobile operator

# uart setting
uart = machine.UART(uart_port, uart_baute)
buffer = deque([], 1000)

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
            return self.uart.read().decode('ignore')
        
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
            send_at("AT+CMGF=1", "OK")  # Set to text mode
            utime.sleep(0.5)

            self.uart.write(f'AT+CMGS="{number}"\r\n'.encode())
            utime.sleep(1)

            self.uart.write(message.encode() + b"\x1A")
            
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
    raise ValueError("[ERROR] SIM868 failed to start.")


def check_gsm():
    print("\n--- GSM MODULE TEST ---")

    print("\n[INFO] Resetting GSM module...")
    send_at("AT+CFUN=1,1", "OK")  # Full modem reset
    print("[INFO] Waiting for module to reboot...")
    utime.sleep(10)

    commands = [
        ("AT", "OK"),
        ("ATE1", "OK"),  # Enable echo
        ("AT+CPIN?", "READY"),  # SIM card ready?
        ("AT+CSQ", "OK"),  # Signal quality
        ("AT+COPS?", "OK"),  # Operator
        ("AT+CREG?", "0,1"),  # GSM network registration
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

    print("\n--- GSM MODULE READY ---")
    return True

def init_device():
    if check_start():
        if check_gsm():
            send_at("AT+CLIP=1", "OK")  # Enable caller ID
            send_at("AT+CMGF=1", "OK")  # Set SMS system into text mode
            utime.sleep(0.5)
            
        else:
            print("[ERROR] GSM setup failed.")
            sys.exit()
    else:
        print("[ERROR] SIM module failed to start.")
        sys.exit()

def read_uart_message():
    return modem.uart_read()

def event_listener():
    print("\n--- STARTING EVENT LISTENER ---")

    while True:
        response = read_uart_message()
        print(f"Uart message: {response}")
        if response:
            buffer.append(response)
        utime.sleep(1)
        
        
def event_handler():
    while True:
        if len(buffer) == 0:
            continue
            utime.sleep(0.1)
        response = buffer.popleft()
        handle_uart_message(response)

def handle_uart_message(response):
    if "RING" in response: # New call has been detected
        print("\n[INFO] Incoming call detected.")
        
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
                
                print(f"[CALLER] Number: {caller_number}")

                if is_number_in_sim(caller_number):
                    print("[INFO] Caller number is in SIM contacts. Hanging up.")
                    modem.hang_up()
                    
                    # Opens the gate
                    
                    caller_number = ""
                else:
                    print("[WARNING] Unknown number. Hanging up.")
                    modem.hang_up()
                    
                    caller_number = "" 

            except Exception as e:
                print("[ERROR] Failed to parse CLIP:", e)
        else:
            print("[ERROR] +CLIP notification not enabled.")
                
    elif "+CMTI:" in response: # New message has been received
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
                    
                except:
                    print("[ERROR] Parsing sender info failed")
                
                print(f"[SMS] From: {sender_number}")
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
        print(f"Response unknown: {response}")

def clean_number(number):
    if number.startswith("+48"):
        number = number[3:]
    return number

def is_number_valid(number):
    number = clean_number(number)
    return number.isdigit() and len(number) == 9
    

def add_contact(number):
    if not is_number_valid(number):
        print("[INFO] Invalid number.")
        resp = "invalid_number"
        return resp
    if is_number_in_sim(number):
        print(f"[INFO] Number already saved.")
        resp = "already_saved"
        return resp
    else:
        name = ""

        number_type = 145 if number.startswith('+') else 129
    
        command = f'AT+CPBW=1,"{number}",{number_type},"{name}"'
        print(f"\nSending: {command}")
        if send_at(command, "OK"):
            print(f"[OK] Contact with number '{number}' saved to SIM.")
            resp = "number_added"
            return resp
        else:
            print(f"[ERROR] Failed to save contact.")
            resp = "failed_to_save"
            return resp
        
def delete_contact(number_to_delete):
    if not is_number_valid(number_to_delete):
        print("[INFO] Invalid number.")
        resp = "invalid_number"
        return resp
    
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
            uart.write(f'AT+CPBW={i}\r\n'.encode())
            utime.sleep(0.2)
            print(f"[OK] Contact with number {number_to_delete} deleted.")
            resp = "number_deleted"
            return resp

    print(f"[INFO] Number {number_to_delete} not found in SIM contacts.")
    resp = "number_not_found"
    return resp

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

                    if sim_number == contact_number:
                        return sim_number
                except:
                    pass
        return None

    except Exception as e:
        print("[ERROR] Could not read SIM contacts:", e)
        return None
           
def sms_command(text): 

    if text.startswith("+"):
        number = text[1:].strip().split()[0]
        resp = add_contact(number)
        if resp == "already_saved":
            print(f"[INFO] Number {number} already saved.")
            message = f"Number {number} already saved."
            return message
        elif resp == "number_added":
            print(f"[OK] Added number: {number}")
            message = f"Number {number} added to SIM card."
            return message
        elif resp == "failed_to_save":
            print(f"[ERROR] Failed to save the number {number}")
            message = f"Failed to save the number {number}"
            return message
        elif resp == "invalid_number":
            print(f"[INFO] Invalid number {number}")
            message = f"Number {number} is not valid."
            return message
        else:
            print(f"[ERROR] Failed to save the number {number}")
            message = f"Failed to save the number {number}"
            return message
        
    elif text.startswith("-"):
        number = text[1:].strip().split()[0]
        resp = delete_contact(number)
        if resp == "number_deleted":
            print(f"[OK] Deleted number: {number}")
            message = f"Number {number} deleted from SIM card."
            return message
        elif resp == "number_not_found":
            print (f"[INFO] Number {number} not found in SIM contacts.")
            message = f"Number {number} not found in SIM contacts."
            return message
        elif resp == "invalid_number":
            print(f"[INFO] Invalid {number}.")
            message = f"Number {number} is not valid."
            return message
        else:
            print (f"[ERROR] Failed to delete number {number}.")
            message = f"Failed to delete number {number}."
            return message
            
        
    elif text.startswith("?"):
        number = text[1:].strip().split()[0]
        is_number_in_sim(number)
        if not is_number_valid(number):
            print("[INFO] Invalid number.")
            message = f"Number {number} is not valid."
            return message
        elif is_number_in_sim(number):
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
def main():
    try:
        init_device()
        
        # Thread #2
        _thread.start_new_thread(event_listener, ())

        # Main thread
        event_handler()
    except Exception as e:
        print(e)
        raise e
    finally:
        # byc moze jakies czyszczenie urzadzenia, jezeli jest potrzebne
        pass

main()

