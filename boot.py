from network import WLAN
import machine
import time
import ujson

print("In boot")
print("Connecting to WiFi....")

wlan = WLAN(mode=WLAN.STA)

def get_wlan_creds():

    creds = {}
    with open("lib/wifi.json", "r") as fp:
        data = fp.read()
        creds = ujson.loads(data)

    ssid = creds.get("ssid", None)
    pwd = creds.get("password", None)

    return ssid, pwd

def main():

    ssid, pwd = get_wlan_creds()

    if ssid is None or pwd is None:
        print("No WLAN credentials found. Aborting wlan connect!")
        return

    wlan.connect(ssid=ssid, auth=(WLAN.WPA2, pwd))
    count = 0
    while not wlan.isconnected():
        time.sleep(5)
        count += 1
        if count > 2:
            machine.reset()

    print("WiFi connected succesfully")
    print(wlan.ifconfig())


main()