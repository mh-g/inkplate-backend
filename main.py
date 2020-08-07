# This is a sample Python script.

import paho.mqtt.client as mqtt
from datetime import datetime
import os
import time
import threading


def publishTime(client):
    now = datetime.now()
    client.publish("/inkplate/in/datetime", now.strftime("%Y %m %d %H %M %S"))


class TimeThread (threading.Thread):
    # publish server time (hourly)
    def run(self):
        while True:
            publishTime(client)
            time.sleep(60 * 60)


def send_config(client):
    client.publish("/inkplate/in/padchecktime", "10", qos=1, retain=True)  # in seconds, must be >= 2s!
    client.publish("/inkplate/in/clockupdate", "60", qos=1, retain=True)  # in seconds, must be >= padchecktime
    client.publish("/inkplate/in/dataupdate", "5", qos=1, retain=True)  # in clockupdate-cycles
    # WLAN times order scheme:
    # 00:00:00 < wlan-on < wlan-off <= 23:59:59
    client.publish("/inkplate/in/wlan-off", "22:00:00", qos=1, retain=True)   # next WLAN turn off time
    client.publish("/inkplate/in/wlan-on", "05:30:00", qos=1, retain=True)   # next WLAN turn on time


def on_connect(client, userdata, flags, rc):
    client.subscribe("/inkplate/out/#")


def on_message(client, userdata, message):
    topic = message.topic.split("/")[3]
    topicDict = {}
    topicDict["buttons"] = handleButtons
    topicDict["menulevel"] = handleMenuLevel
    topicDict["battery"] = handleBattery
    topicDict["temperature"] = handleTemperature
    topicDict["pressure"] = handlePressure
    topicDict["humidity"] = handleHumidity
    topicDict["reset"] = handleReset
    handler = topicDict.get(topic)
    if handler:
        handler(client, message.payload)
    else:
        print("Unknown topic coming in (else):", message.topic)


def handleButtons(aClient, aButtons):
    buttons = int(aButtons)
#    if buttons & 1:
#        print("pad 1 touched")
#    if buttons & 2:
#        print("pad 2 touched")
#    if buttons & 4:
#        print("pad 3 touched")


def handleMenuLevel(aClient, aMenuLevel):
    menuLevel = int(aMenuLevel)
    print("Menu level %d" % menuLevel)


def handleBattery(aClient, aBattery):
    battery = float(aBattery)
#    print("Battery %f" % battery)


def handleTemperature(aClient, aTemperature):
    temperature = float(aTemperature)
#    print("Temperature %f" % temperature)


def handlePressure(aClient, aPressure):
    pressure = float(aPressure)
#    print("Pressure %f" % pressure)


def handleHumidity(aClient, aHumidity):
    humidity = float(aHumidity)
#    print("Humidity %f" % humidity)


def handleReset(aClient, aReset):
    def publishEnvSensors(which):
        def appendFile(filename):
            f = open(filename, "r")
            message = f.readline() + "@"
            f.close()
            return message

        message = ""
        path = "/tmp/weather"
        if which == "indoor":
            path = "/tmp/inkplate"
        elif which == "outdoor":
            path = "/tmp/weather"
        else:
            return

        if not os.path.exists(path):
            message = "<Keine Daten>"
        else:
            message = appendFile(path + "/temperature") \
                      + appendFile(path + "/pressure") \
                      + appendFile(path + "/humidity") \
                      + appendFile(path + "/battery")
            modificationTime = time.localtime(os.path.getmtime(path + "/temperature"))
            message += time.strftime("%H:%M", modificationTime)
        aClient.publish("/inkplate/in/"+which, message, qos=1, retain=True)

    publishTime(client)
    publishEnvSensors("indoor")
    publishEnvSensors("outdoor")

    # power (mh: needs to implement access to real data!)
    day = "02.08.2020"
    consumption = 6.789
    assessmentConsumption = "0"
    production = 0.123
    assessmentProduction = "-1"
    aClient.publish ("/inkplate/in/power", f"{day}@{consumption}@{assessmentConsumption}@{production}@{assessmentProduction}", qos=1, retain=True)

    # Bahnhofsinfo Gettorf (mh: needs to implement access to real data!)
    station = "Zuege Gettorf - Kiel"
    train1 = "--:-- ---"
    train2 = "--:-- ---"
    train3 = "--:-- ---"
    aClient.publish ("/inkplate/in/station", f"{station}@{train1}@{train2}@{train3}", qos=1, retain=True)

    # MOTD (mh: needs to implement access to real data!)
    line1 = ""
    line2 = ""
    aClient.publish ("/inkplate/in/motd", f"{line1}@{line2}", qos=1, retain=True)


if __name__ == '__main__':
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("mediaberry")

    send_time = TimeThread()
    send_time.start()

    send_config(client)

    client.loop_forever()
