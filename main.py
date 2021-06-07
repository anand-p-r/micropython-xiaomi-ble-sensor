import time
import ujson
import machine
import utime
from machine import RTC
from network import Bluetooth
from mqtt import MQTTClient


## Constants
hexdigits = "0123456789abcdefABCDEF"
MAC_MQTT_DICT = {}
MQTT_CLIENT = None
LONG_SLEEP = False
LONG_SLEEP_DUR = (1*60)
SHORT_SLEEP_DUR = 1
WEAK_CONN_RETRY_ATT = 2
ECONNRESET_RETRY_TIMER = 2
NTP_SYN_WAIT_TIMER = 2
ADV_LISTEN_WAIT_TIMER = 0.050

BOARD_TELEMETRY_TOPIC = None
rtc = None


## Class to hold device specific topic and other MQTT details
class Device:
    def __init__(self, name, sensor_topic, availability_topic, average, timeout, retain):
        self.name         = name
        self.sensor_topic = sensor_topic
        self.avail_topic  = availability_topic
        self.average      = average
        self.timeout      = timeout
        self.retain       = retain

        self.cumulative_temp  = 0.0
        self.cumulative_rh    = 0.0
        self.temp_data_points = 0
        self.rh_data_points   = 0
        self.battery_percent  = 0.0
        self.mqtt_sent        = False

    def update_temp(self, temp):
        self.cumulative_temp  += temp
        self.temp_data_points += 1

    def update_rh(self, rh):
        self.cumulative_rh  += rh
        self.rh_data_points += 1

    def update_battery(self, battery_percent):
        self.battery_percent = battery_percent

    def get_avg_temp(self):
        return round(self.cumulative_temp/self.temp_data_points, 1)

    def get_avg_rh(self):
        return round(self.cumulative_rh/self.rh_data_points, 1)

    def get_battery_percent(self):
        return self.battery_percent

    def reset_avg_values(self):
        self.cumulative_temp  = 0
        self.cumulative_rh    = 0.0
        self.temp_data_points = 0
        self.rh_data_points   = 0
        self.battery_percent  = 0.0

    def print_all_values(self):
        print(self.cumulative_temp, self.cumulative_rh, 
            self.temp_data_points, self.rh_data_points, 
            self.battery_percent, self.mqtt_sent)


def init_mqtt_connection():
    '''
    Initialise MQTT client
    '''
    global MQTT_CLIENT
    global BOARD_TELEMETRY_TOPIC

    config_data = {}
    with open("lib/mqtt.json", "r") as fp:
        data = fp.read()
        config_data = ujson.loads(data)

    client_id = config_data.get("client", None)
    host = config_data.get("host", None)
    port = config_data.get("port", None)
    user = config_data.get("user", None)
    password = config_data.get("password", None)
    
    ## Topic for board diagnostics
    BOARD_TELEMETRY_TOPIC = config_data.get("board_telemetry_topic", None)

    try:
        MQTT_CLIENT = MQTTClient(client_id, str(host), user=str(user), password=str(password), port=int(port))
        MQTT_CLIENT.connect()
        print("Successfully connected to MQTT Broker @ {}:{}".format(host, port))
    except Exception as e:
        print ("MQTT connection failed due to {}".format(e))
    

def init_devices():
    '''
    Initialise sensors
    '''

    device_list = []
    with open("lib/devices.json", "r") as fp:
        data = fp.read()
        device_list = ujson.loads(data)

    for device in device_list:
        name = device.get("name", None)
        sensor_topic = device.get("sensor_topic", None)
        avail_topic = device.get("avail_topic", None)
        average = device.get("average", None)
        timeout = device.get("timeout", None)
        retain = device.get("retain", None)
        mac = device.get("mac", None)
    
        try:
            device = Device(str(name), str(sensor_topic), str(avail_topic), int(average), int(timeout), int(retain))
            device_mac = mac
            device_key = get_key(device_mac)
            MAC_MQTT_DICT[device_key] = device
            print("Successfully added device {} with mac {}".format(name, mac))
        except Exception as e:
            print("Device could not be added due to {}".format(e))


def reset_mqtt_sent():
    for mac in MAC_MQTT_DICT:
        MAC_MQTT_DICT[mac].mqtt_sent = False


def time_for_long_sleep():
    
    mqtt_count = 0
    for mac in MAC_MQTT_DICT:
        if MAC_MQTT_DICT[mac].mqtt_sent:
            mqtt_count += 1
    
    if mqtt_count == len(MAC_MQTT_DICT):
        reset_mqtt_sent()
        return True
    
    return False


def get_board_temperature():

    deg_cel = 0.0
    try:
        deg_cel = round(((machine.temperature() - 32) * (5/9)), 2)
    except Exception as e:
        print("Unable to convert board temperature!")

    return deg_cel

def send_on_mqtt(msgs=None):

    if MQTT_CLIENT and msgs:
        for msg in msgs:
            topic = msg.get("topic", None)
            retain = msg.get("retain", True)
            if topic:
                try:
                    MQTT_CLIENT.publish(topic=topic, msg=ujson.dumps(msg.get("payload")), retain=retain)
                except Exception as e:
                    print("MQTT Publish Exception - {}".format(e))
                    raise e
            else:
                print("No topic defined")
    else:
        print("No MQTT_CLIENT or msg")

def get_key(mac):

    mac = mac.lower()
    reverse_mac = ""

    count = 0
    ap_str = ""
    for i in reversed(mac):
        ap_str = ap_str + i
        count += 1
        if count == 2:
            reverse_mac = reverse_mac + ap_str[1] + ap_str[0]
            ap_str = ""
            count = 0
    
    return reverse_mac


def get_hex_val(str_with_escape):

    if str_with_escape == "\\n":
        return "0a"
    elif str_with_escape == "\\r":
        return "0d"
    elif str_with_escape == "\\f":
        return "0c"
    elif str_with_escape == "\\t":
        return "09"
    elif str_with_escape == "\\v":
        return "0b"
    elif str_with_escape == "\\0":
        return "00"
    elif str_with_escape == "\\b":
        return "08"
    elif str_with_escape == "\\\\":
        return "5c"


def get_hex_from_string(raw_string):

    ## Splt string with \x to get the hex values
    str_split_vals = raw_string.split("\\x")

    hex_str = ""

    ## Ignore the first substring which is b'
    ## If length is > 2, there are extra chars
    ## which have ti be convereted to 
    ## hex(ascii value). Extra chars may also 
    ## have escape chars that have to be 
    ## replaced with their respective
    ## hex(ascii value)
    for item in str_split_vals[1:]:
        if len(item) == 2:
            hex_str = hex_str + item
        elif len(item) > 2:
            hex_str = hex_str + item[0:2]

            chr_indx = 0
            extra_chars_escapes = item[2:]
            while chr_indx < len(extra_chars_escapes):
                chr = extra_chars_escapes[chr_indx]
                if chr == "\\":
                    hex_val = get_hex_val(extra_chars_escapes[chr_indx:chr_indx+2])
                    chr_indx += 1
                else:
                    ascii_val = ord(chr)
                    hex_val = hex(ascii_val).replace("0x", "")
                hex_str = hex_str + hex_val
                chr_indx += 1
    
    return hex_str


def adjust_digits(raw_int_val):

    if len(str(raw_int_val)) > 3:
        return raw_int_val/100
    elif len(str(raw_int_val)) == 3:
        return raw_int_val/10
    else:
        return raw_int_val


def get_device(mac):

    if mac in MAC_MQTT_DICT.keys():
        return MAC_MQTT_DICT[mac]
    
    return None


def decode_service_data(data_as_bytes, last_reset_ts=None):

    global rtc

    try:
        ## Convert bytes to string
        str_data = str(data_as_bytes)

        ## Remove hex prfix and replace escapre chars with their 
        ## respective hex value of ascii value
        hex_str = get_hex_from_string(str_data)

        service_uuid = hex_str[0:4]
        ##print("Service UUID - {}".format(service_uuid))

        frame_control = hex_str[4:8]
        ##print("Frame Control - {}".format(frame_control))

        id = hex_str[8:12]
        ##print("Id - {}".format(id))

        index = hex_str[12:14]
        ##print("Index - {}".format(index))

        mac = hex_str[14:26]
        print("Mac - {}".format(mac))

        device = get_device(mac)
        
        if device == None:
            print("Mac filtered!")
            return

        ## Now the game starts
        data_type = hex_str[26:30]
        ##print("Data Type - {}".format(data_type))

        length = hex_str[30:32]
        ##print("Length - {}".format(length))
        length = int(length)

        value = hex_str[32:(32+(length*2))]

        if data_type == "0a10":
            battery_value = int(value, 16)
            battery_value = adjust_digits(battery_value)
            print("Battery % - {}".format(battery_value))
            device.update_battery(battery_value)

        elif data_type == "0d10":
            temp_value = value[2:4] + value[0:2]
            temp_value = int(temp_value, 16)
            temp_value = adjust_digits(temp_value)
            print("Temp deg - {}".format(temp_value))
            device.update_temp(temp_value)
            
            rh_value = value[6:8] + value[4:6]
            rh_value = int(rh_value, 16)
            rh_value = adjust_digits(rh_value)
            print("RH % - {}".format(rh_value))
            device.update_rh(rh_value)

        elif data_type == "0610":
            ##print("Humidity received")
            rh_value = value[2:4] + value[0:2]
            rh_value = int(rh_value, 16)
            rh_value = adjust_digits(rh_value)
            print("RH % - {}".format(rh_value))
            device.update_rh(rh_value)

        elif data_type == "0410":
            ##print("Temp received")
            temp_value = value[2:4] + value[0:2]
            temp_value = int(temp_value, 16)
            temp_value = adjust_digits(temp_value)
            print("Temp deg - {}".format(temp_value))
            device.update_temp(temp_value)

        device.print_all_values()

        if device.temp_data_points >= device.average and device.rh_data_points >= device.average and device.battery_percent > 0.0:
            availability = "offline"
            messages = []

            ## Data payload
            payload = {
                        "temperature": device.get_avg_temp(),
                        "humidity": device.get_avg_rh(),
                        "battery": device.get_battery_percent(),
                        "average": device.average
                    }

            data_dict = {
                "topic": device.sensor_topic,
                "payload": payload,
                "retain": bool(int(device.retain))
            }
            messages.append(data_dict)

            ## Availability payload. Can be improved to report device avail.
            availability = "online"
            avail_dict = {
                "topic": device.avail_topic,
                "payload": availability,
                "retain": bool(int(device.retain))
            }
            messages.append(avail_dict)

            ## Board telemetry
            if BOARD_TELEMETRY_TOPIC is not None:
                payload = {
                    "temperature": get_board_temperature(),
                    "last_reset_ts": last_reset_ts
                }

                board_temp_dict = {
                    "topic": BOARD_TELEMETRY_TOPIC,
                    "payload": payload,
                    "retain": True
                }

                messages.append(board_temp_dict)
            
            ## For weak connections
            count_conn = 0
            while count_conn < WEAK_CONN_RETRY_ATT:
                try:
                    ## Publish on MQTT
                    send_on_mqtt(messages)
                    print("{}: MQTT sent message - {}".format(rtc.now(), messages))
                    device.mqtt_sent = True
                    device.reset_avg_values()
                    count_conn = 0
                    break
                except Exception as e:
                    print("MQTT sending exception - {}. Retry attempt {}".format(e, count_conn+1))
                    time.sleep(int(ECONNRESET_RETRY_TIMER))
                    count_conn += 1
            
            ## Reset if conn is still broken
            if count_conn >= WEAK_CONN_RETRY_ATT:
                print("Retry attempts exceeded! Will reset the board and retry")
                machine.reset()

    except Exception as e:
        print("Data parsing exception - {}".format(e))


def format_ts_to_string(ts_as_list):

    utime.timezone(10800)
    ts_as_list = utime.localtime()
    ts_string = "-".join([str(s) for s in ts_as_list[:-2]])
    return ts_string


def main():
    global rtc

    rtc = RTC()
    rtc.ntp_sync("pool.ntp.org")

    while not rtc.synced():
        print("NTP sync not complete! Lets wait for a while!")
        time.sleep(int(NTP_SYN_WAIT_TIMER))

    print("NTP sync completed!")

    init_mqtt_connection()
    init_devices()
    last_reset_ts = format_ts_to_string(rtc.now())

    bt = Bluetooth()

    try:
        bt.start_scan(-1)
        print("Starting scan!")
    except:
        print("Stopping existing scan!")
        bt.stop_scan()

        print("Starting new scan!")
        bt.start_scan(-1)

    while True:
        adv = bt.get_adv()

        if adv:
            try:
                # try to get the complete name
                adv_name = bt.resolve_adv_data(adv.data, Bluetooth.ADV_NAME_CMPL)
            except Exception as e:
                print("Error while connecting or reading from the BLE device - ", e)
                
            if adv_name:
                if "MJ_HT_V" in adv_name:
                    data = bt.resolve_adv_data(adv.data, Bluetooth.ADV_SERVICE_DATA)
                    print("Service data: {}".format(data))
                    decode_service_data(data, last_reset_ts)

                    if time_for_long_sleep():
                        time.sleep(LONG_SLEEP_DUR)
                    else:
                        time.sleep(SHORT_SLEEP_DUR)
        else:
            time.sleep(float(ADV_LISTEN_WAIT_TIMER))


main()