import os
import threading
import time
from datetime import datetime
from datetime import timedelta
import paho.mqtt.client as mqtt
import rrdtool

def publishTime(client):
    now = datetime.now()
    client.publish("/inkplate/in/datetime", now.strftime("%Y %m %d %H %M %S"))


def publishTrains(client):
    # Bahnhofsinfo Gettorf (mh: needs to implement access to real data!)
    trains = "Abfahrten Gettorf@--:--@--:--@--:--@--:--"
    try:
        if os.path.exists("/tmp/station-Gettorf.txt"):
            with open("/tmp/station-Gettorf.txt", "r") as f:
                trains = f.readline ()
            f.close()
    except Exception as e:
        print("error reading station file:", e)
    client.publish ("/inkplate/in/station", trains, qos=1, retain=True)


class TimeThread (threading.Thread):
    # publish server time and station info (once per minute)
    def run(self):
        while True:
            publishTrains(client)
            publishTime(client)
            time.sleep(60)


def send_config(client):
    def send_udpaterates(client):
        now = datetime.now()
        clockupdate = 3600 # clock and data updates hourly, pad checked hourly
        dataupdate = 1
        padchecktime = 3600
        if now.hour in range(5, 8): # clock is up to date, data max 5 mins old, pad checked every 10 secs
            clockupdate = 60
            dataupdate = 5
            padchecktime = 10
        elif now.hour in range(8, 21): # clock is up to date, data max 30 mins old, pad checked every 60 secs
            clockupdate = 60
            dataupdate = 30
            padchecktime = 60
        client.publish("/inkplate/in/clockupdate", str(clockupdate), qos=1, retain=True)  # in seconds, must be >= padchecktime
        client.publish("/inkplate/in/dataupdate", str(dataupdate), qos=1, retain=True)  # in clockupdate-cycles
        client.publish("/inkplate/in/padchecktime", "10", qos=1, retain=True)  # in seconds, must be >= 2s!

    send_udpaterates(client)
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


def handleTemperature(aClient, aTemperature):
    temperature = float(aTemperature)


def handlePressure(aClient, aPressure):
    pressure = float(aPressure)


def handleHumidity(aClient, aHumidity):
    humidity = float(aHumidity)


def handleReset(aClient, aReset):
    def publishEnvSensors(which):
        def appendFile(filename, digits):
            f = open(filename, "r")
            value = float(f.readline())
            f.close()
            if (digits == 1):
                message = "{:.1f}".format (value) + "@"
            elif (digits == 2):
                message = "{:.2f}".format (value) + "@"
            else:
                message = str(value) + "@"
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
            message = appendFile(path + "/temperature", 1) \
                      + appendFile(path + "/pressure", 1) \
                      + appendFile(path + "/humidity", 1) \
                      + appendFile(path + "/battery", 2)
            modificationTime = time.localtime(os.path.getmtime(path + "/temperature"))
            message += time.strftime("%H:%M", modificationTime)
            message = message.replace (" ", "")
        aClient.publish("/inkplate/in/"+which, message, qos=1, retain=True)

    def publishPower():
        # power (mh: needs to implement access to real data!)
        today = datetime.now()
        database = "/srv/dev-disk-by-label-DISK1/localdata/powermeter.rrd"
        max = rrdtool.fetch (database, "MAX", "--start=" + today.strftime("%Y%m%d"), "--end=" + today.strftime('%Y%m%d'))
        yesterday = today - timedelta (days = 1)
        min = rrdtool.fetch (database, "MAX", "--start=" + yesterday.strftime("%Y%m%d"), "--end=" + yesterday.strftime('%Y%m%d'))
        day = yesterday.strftime ("%d.%m.%Y")
        consumption = max[2][0][0] - min[2][0][0]
        if (consumption < 0.001):
            assessmentConsumption = "2"
        elif (consumption < 1):
            assessmentConsumption = "1"
        elif (consumption < 5.0):
            assessmentConsumption = "0"
        elif (consumption < 7.0):
            assessmentConsumption = "1"
        else:
            assessmentProduction = "2"
        production = max[2][0][1] - min[2][0][1]
        if (production < 0.001):
            assessmentProduction = "-2"
        elif (production < 0.1):
            assessmentProduction = "-1"
        elif (production < 0.5):
            assessmentProduction = "0"
        elif (production < 0.9):
            assessmentProduction = "1"
        else:
            assessmentProduction = "2"
        aClient.publish ("/inkplate/in/power", f"{day}@{consumption:.3f}@{assessmentConsumption}@{production:.3f}@{assessmentProduction}", qos=1, retain=True)

    def publishMOTD():
        # MOTD (mh: needs to implement access to real data!)
        line1 = ""
        line2 = ""
        aClient.publish ("/inkplate/in/motd", f"{line1}@{line2}", qos=1, retain=True)

    send_config(aClient)
    print ("handleReset")
    publishTime(client)
    print (". time")
    publishEnvSensors("indoor")
    print (". indoor")
    publishEnvSensors("outdoor")
    print (". outdoor")
    publishPower()
    print (". power")
    publishTrains(client)
    print (". trains")
    publishMOTD()
    print (". motd")
    print ("... done")


if __name__ == '__main__':
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("mediaberry")

    send_time = TimeThread()
    send_time.start()

    send_config(client)

    client.loop_forever()
