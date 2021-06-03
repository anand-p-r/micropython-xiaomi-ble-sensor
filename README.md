# micropython-xiaomi-ble-sensor
Micropython script that runs on a [PyCom GPy](https://docs.pycom.io/) board to parse and transmit BLE temperature, humidity and battery sensor values via MQTT over WiFi.

## Supported Devices
[LYWSDCGQ](https://esphome.io/components/sensor/xiaomi_ble.html#lywsdcgq)


## Configuration
1. Update lib/wifi.json with the WiFi credentials.
2. Update lib/mqtt.json with MQTT Broker address and credentials.
3. Update lib/devices.json with Sensor/Device details.

Sensor values are collected and aggregated every 15mins. Flash the project to a PyCom board and see it colect sensor values.

## References
1. [PyMakr VSCode](https://marketplace.visualstudio.com/items?itemName=pycom.Pymakr) plugin for development
2. [PyCom WLAN](https://docs.pycom.io/firmwareapi/pycom/network/wlan/) setup
3. [PyCom BLE](https://docs.pycom.io/firmwareapi/pycom/network/bluetooth/) setup
4. Sensor data parsing instructions and examples were borrowed from [here](https://github.com/hannseman/homebridge-mi-hygrothermograph).

## Original Author
Anand Radhakrishnan: @anand-p-r
