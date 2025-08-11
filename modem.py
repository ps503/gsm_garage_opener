import machine
import os
import utime
import binascii
import _thread
import sys

# using pin defined
pwr_en = 14  # pin to control the power of the module
uart_port = 0
uart_baute = 115200

APN = "internet" #defined for the mobile operator

uart = machine.UART(uart_port, uart_baute)
uart_lock = _thread.allocate_lock()

INTERNATIONAL = 145
UNKNOWN = 129

GK_numbers = [
    "+48503815525"
]

class Modem:
    
    def __init__(self, port, baute):
        self.uart = machine.UART(port, baute)
        self.uart_lock = _thread.allocate_lock()
        
    def wait_resp_info(self, timeout=2000):
        """
        Waits for response from modem.
        
        :param timeout: time in milliseconds
        :return: raw modem response
        """
        prvmills = utime.ticks_ms()
        info = b""
        while (utime.ticks_ms()-prvmills) < timeout:
            if uart.any():
                info = b"".join([info, uart.read(1)])
        print(info.decode())
        return info
    
    def power_on_off(self):
        """
        Powers on/off the modem.
        """
        pwr_key = machine.Pin(pwr_en, machine.Pin.OUT)
        pwr_key.value(1)
        utime.sleep(2)
        pwr_key.value(0)

    def send_at(self, cmd, back, timeout=2000):
        """
        Sends AT command to the modem and waits for the response.
        
        :param cmd: AT command
        :param back: expected response from modem
        :param timeout: timeout in milliseconds
        :return: True if expected response found, False otherwise
        """
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
            
    def check_gsm(self):
        """
        Initialize GSM: SIM check, signal quality, operator
        
        :return: True if GSM module is ready, False otherwise
        """
        print("\n--- GSM MODULE TEST ---")

        print("\n[INFO] Resetting GSM module...")
        self.full_reset()
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
            success = self.send_at(cmd, expected_response)
            if success:
                print("[OK]")
            else:
                print(f"[ERROR] Command failed: {cmd}")
                return False  

        print("\n--- GSM MODULE READY ---")
        return True

    def check_start(self):
        """
        Checks if modem is ready by sending AT commands.
        
        :return: True if modem responds with "OK", False otherwise
        """
        for i in range(3):  
            with uart_lock:
                uart.write(b'ATE1\r\n')
            utime.sleep(2)
            with uart_lock:
                uart.write(b'AT\r\n')
            rec = self.wait_resp_info()
            if "OK" in rec.decode():
                print("[OK] SIM868 is ready")
                return True
            else:
                self.power_on_off()
                print("[INFO] Restarting SIM868...")
                utime.sleep(8)
        raise ValueError("[ERROR] SIM868 failed to start.")

    def init_device(self):
        """
        Initializes the modem: checks startup, configures GSM, enables caller ID and configurates SMS settings.
        """
        if self.check_start():
            if self.check_gsm():
                self.enable_caller_id()
                self.text_mode()
                utime.sleep(0.5)
            
            else:
                print("[ERROR] GSM setup failed.")
                sys.exit()
        else:
            print("[ERROR] SIM module failed to start.")
            sys.exit()
        
    def full_reset(self):
        """
        Full modem reset.
        
        :return: raw modem response ("OK" on success)
        """
        return self.send_at("AT+CFUN=1,1", "OK")
    
    def text_mode(self):
        """
        Sets system into text mode.
        
        :return: raw modem response ("OK" on success)
        """
        return self.send_at("AT+CMGF=1", "OK")
    
    def enable_caller_id(self):
        """
        Enables caller ID.
        
        :return: raw modem response ("OK" on success)
        """
        return self.send_at("AT+CLIP=1", "OK")

    def hang_up(self):
        """
        Hangs up the current call.
        """        
        with self.uart_lock:
            self.uart.write(b"ATH\r\n")
            
    def get_contact_range(self):
        """
        Returns available contact index range stored on the SIM card.
        
        :return: raw modem response (+CPBR: (1-250),...)
        """
        with self.uart_lock:
            self.uart.write(b'AT+CPBR=?\r\n') 
            utime.sleep(0.5)
            resp = self.uart.read().decode('ignore')
            return resp

    def read_sms_by_index(self, sms_index):
        """
        Reads SMS from a specific memory index.
        
        :param sms_index: the index of the SMS message to read
        :return: raw modem response containing the SMS header and message body
        """
        with self.uart_lock:
            self.uart.write(b"AT+CMGF=1\r\n")  # Set to text mode
            utime.sleep(0.2)
            
            self.uart.write(f"AT+CMGR={sms_index}\r\n".encode())
            utime.sleep(0.5)
            return self.uart.read().decode('ignore')
        
    def read_contact(self, i):
        """
        Reads a single contact entry from the SIM card phonebook.
        
        :param i: index of contact to read
        :return: raw modem response in the format: +CPBR: <index>,<number>,<type>,<text>
        """
        with self.uart_lock:
            self.uart.write(f'AT+CPBR={i}\r\n'.encode())
            utime.sleep(0.3)
            entry = self.uart.read().decode('ignore')
            return entry
        
            
    def delete_sms(self, sms_index):
        """
        Deletes message from the SIM card.

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
        Sends SMS message to the given phone number.

        :param number: recipient's phone number
        :param message: message content
        """
        with self.uart_lock:
            self.text_mode()
            utime.sleep(0.5)

            self.uart.write(f'AT+CMGS="{number}"\r\n'.encode())
            utime.sleep(1)

            self.uart.write(message.encode() + b"\x1A")
            
    def uart_read(self):
        """
        Reads and decodes uart response.

        :return: decoded uart response or an empty string if no data is available
        """
        with self.uart_lock:
            if self.uart.any():
                return self.uart.read().decode('ignore')
            else:
                return ""
            
    def delete_all_messages(self):
        """
        Deletes all SMS messages from the SIM card.
        
        :return: raw modem response ("OK" on success)
        """
        return self.send_at("AT+CMGD=1,4", "OK")
    
    def clean_number(self, number):
        """
        Removes the "+48" country code prefix from a phone number, if present.
        
        :param number: phone number
        :return: phone number without "+48" prefix 
        """
        if number.startswith("+48"):
            number = number[3:]
        return number

    def is_number_valid(self, number):
        """
        Checks if a phone number is valid (exactly 9 digits after cleaning).
        
        :param number: phone number to validate
        :return: True if the number is valid, False otherwise
        """
        number = self.clean_number(number)
        return number.isdigit() and len(number) == 9
    
    def is_number_in_sim(self, contact_number):
        """
        Checks if a given phone number is stored in the SIM card's phonebook.
        
        :param contact_number: phone number to search for
        :return: the stored number if found, None otherwise
        """
        resp = self.get_contact_range()

        try:
            start = resp.index('(') + 1
            end = resp.index(')')
            index_range = resp[start:end]
            min_idx, max_idx = [int(x) for x in index_range.split('-')]

            for i in range(min_idx, max_idx + 1):
                entry = self.read_contact(i)

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
    
    def is_number_GK(self, number):
        """
        Checks if a given number belongs to the Gate Keeper (GK) admin.
        
        :param number: phone number to check
        :return: True if the number is in the GK list, False otherwise
        """
        return number in GK_numbers     
    
    def add_contact(self, number):
        """
        Adds a contact to the SIM card if it is valid and not already saved.
        
        :param number: phone number to add
        :return: status string: "number_added", "already_saved", "invalid_number" or "failed_to_save"
        """
        if not self.is_number_valid(number):
            print("[INFO] Invalid number.")
            resp = "invalid_number"
            return resp
        if self.is_number_in_sim(number):
            print(f"[INFO] Number already saved.")
            resp = "already_saved"
            return resp
        else:
            name = ""

            number_type = INTERNATIONAL if number.startswith('+') else UNKNOWN
    
            command = f'AT+CPBW=1,"{number}",{number_type},"{name}"'
            print(f"\nSending: {command}")
            if self.send_at(command, "OK"):
                print(f"[OK] Contact with number '{number}' saved to SIM.")
                resp = "number_added"
                return resp
            else:
                print(f"[ERROR] Failed to save contact.")
                resp = "failed_to_save"
                return resp
            
    def delete_contact(self, number):
        """
        Deletes a contact from the SIM card phonebook.
        
        :param number: phone number to delete
        :return: status string: "number_deleted", "number_not_found" or "invalid_number"
        """
        if not self.is_number_valid(number):
            print("[INFO] Invalid number.")
            resp = "invalid_number"
            return resp
    
        response = self.get_contact_range()
    
        try:
            start = response.index('(') + 1
            end = response.index(')')
            index_range = response[start:end]
            min_idx, max_idx = [int(x) for x in index_range.split('-')]

        except:
            print("[ERROR] Failed to parse index range")
            return
    
        for i in range(min_idx, max_idx + 1):
            entry = self.read_contact(i)
            if number in entry:
                print(f"[INFO] Found number at index {i}, deleting...")
                uart.write(f'AT+CPBW={i}\r\n'.encode())
                utime.sleep(0.2)
                print(f"[OK] Contact with number {number} deleted.")
                resp = "number_deleted"
                return resp

        print(f"[INFO] Number {number} not found in SIM contacts.")
        resp = "number_not_found"
        return resp
    
    def sms_command(self, text):
        """
        Returns text of the response to send depending on the received message
        
        :param text: the received SMS message text
        :return: response text to send back via SMS, or None if no reply is needed
        """

        if text.startswith("+"):
            number = text[1:].strip().split()[0]
            resp = self.add_contact(number)
            if resp == "already_saved":
                message = f"Number {number} already saved."
                print(f"[INFO] {message}")
                return message
            elif resp == "number_added":
                message = f"Number {number} added to SIM card."
                print(f"[OK] {message}")
                return message
            elif resp == "failed_to_save":
                message = f"Failed to save the number {number}"
                print(f"[ERROR] {message}")
                return message
            elif resp == "invalid_number":
                message = f"Number {number} is not valid."
                print(f"[INFO] {message}")
                return message
            else:
                message = f"Failed to save the number {number}"
                print(f"[ERROR] {message}")
                return message
        
        elif text.startswith("-"):
            number = text[1:].strip().split()[0]
            resp = self.delete_contact(number)
            if resp == "number_deleted":
                message = f"Number {number} deleted from SIM card."
                print(f"[OK] {message}")
                return message
            elif resp == "number_not_found":
                message = f"Number {number} not found in SIM contacts."
                print(f"[INFO] {message}")
                return message
            elif resp == "invalid_number":
                message = f"Number {number} is not valid."
                print(f"[INFO] {message}")
                return message
            else:
                message = f"Failed to delete number {number}."
                print(f"[ERROR] {message}")
                return message
            
        
        elif text.startswith("?"):
            number = text[1:].strip().split()[0]
            if not self.is_number_valid(number):
                message = f"Number {number} is not valid."
                print(f"[INFO] {message}")
                return message
            elif self.is_number_in_sim(number):
                message = f"Number {number} is in SIM card."
                print(f"[INFO] {message}")
                return message
            else:
                message = f"Number {number} not found."
                print(f"[INFO] {message}")
                return message

        elif text.startswith("W trakcie") or text.startswith("Masz"):
            return
    
        else:
            print("[ERROR] Unknown command.")
            message = f"Unknown command. Use +, - or ?."
            print(f"[ERROR] {message}")
            return message
    
    def send_sms(self, number, message):
        """
        Sends an SMS message and waits for confirmation.
        
        :param number: recipient's phone number
        :param message: message content
        """   
        print(f"[INFO] Sending SMS to {number}...")

        try:
            self.send_sms_text(number, message)

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
            
    def handle_uart_message(self, response):
        """
        Handles and processes a raw UART message from the modem.
        
        :param response: raw UART response from the modem
        """
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

                    if self.is_number_in_sim(caller_number):
                        print("[INFO] Caller number is in SIM contacts. Hanging up.")
                        self.hang_up()
                    
                        # Opens the gate
                    
                        caller_number = ""
                    else:
                        print("[WARNING] Unknown number. Hanging up.")
                        self.hang_up()
                    
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
                    
                sms_resp = self.read_sms_by_index(sms_index)
                
                print(f"[INFO] Text of SMS: {sms_resp}")

                lines = sms_resp.splitlines()
                header = lines[5] if len(lines) > 0 else "" # number, name, date, ...
                text = "\n".join(lines[6:]).strip()
                print(f"[DEBUG] SMS Header: {header}")

                try:
                    header_parts = header.split('"')
                    sender_number = header_parts[3] if len(header_parts) > 3 else "Unknown"
                    
                except:
                    print("[ERROR] Parsing sender info failed")
                
                print(f"[SMS] From: {sender_number}")
                print(f"[SMS] Message: {text}")
                
                # Max 25 messages
                if sms_index > 24:
                    resp = self.delete_all_messages()
                    if resp and "OK" in resp:
                        print("[INFO] All messages deleted.")
                    else:
                        print("[WARNING] Failed to delete all messages.")
                else:
                    print(f"[INFO] Deleting SMS at index: {sms_index}")
                    self.delete_sms(sms_index)
                
                if self.is_number_GK(sender_number):
                    print(f"[INFO] Sender number is GK.")
                    message = self.sms_command(text)
                    if message:
                        self.send_sms(sender_number, message)
                    
                else:
                    print(f"[INFO] Not GK number.")
                
            except Exception as e:
                print("[ERROR] Failed to parse SMS:", e)
                
        else:
            print(f"Response unknown: {response}")
    