import os
import sys
import threading
import time
from datetime import datetime, date, timedelta
import paho.mqtt.client as mqtt
import rrdtool
from PIL import Image

## We'll try to use the local caldav library, not the system-installed
sys.path.insert(0, '..')
import caldav
import icalendar
from calendarcredentials import url, username, password

def publishTime(client):
    now = datetime.now()
    client.publish("/inkplate/in/datetime", now.strftime("%Y %m %d %H %M %S"))


def publishTrains(client):
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
        lastHour = -1
        while True:
            now = datetime.now()
            if now.hour != lastHour:
                lastHour = now.hour
                fullUpdate(client)
                pictureUpdate()

            publishTrains(client)
            publishTime(client)
            time.sleep(60)


def send_config(client):
    def send_udpaterates(client):
        now = datetime.now()
        clockupdate = 3600 # clock and data updates hourly, pad checked hourly
        dataupdate = 1
        padchecktime = 3600
        if now.hour in range(4, 8): # clock is up to date, data max 5 mins old, pad checked every 10 secs
            clockupdate = 60
            dataupdate = 5
            padchecktime = 10
        elif now.hour in range(8, 22): # clock is up to date, data max 30 mins old, pad checked every 60 secs
            clockupdate = 300 # 60
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
    fullUpdate(aClient)


def fullUpdate(aClient):
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
            message = message.replace (" ", "")
            message += time.strftime("%d.%m._%H:%M", modificationTime)
        aClient.publish("/inkplate/in/"+which, message, qos=1, retain=True)

    def publishPower():
        # power (mh: needs to implement access to real data!)
        today = datetime.now()
        database = "/srv/dev-disk-by-label-DISK1/localdata/powermeter.rrd"
        max = rrdtool.fetch (database, "MAX", "--start=" + today.strftime("%Y%m%d"), "--end=" + today.strftime('%Y%m%d'))
        yesterday = today - timedelta (days = 1)
        min = rrdtool.fetch (database, "MAX", "--start=" + yesterday.strftime("%Y%m%d"), "--end=" + yesterday.strftime('%Y%m%d'))
        day = yesterday.strftime ("%d.%m.")
        consumption = max[2][0][0] - min[2][0][0]
        assessmentConsumption = 0
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
        assessmentProduction = 0
        if (production < 0.001):
            if production < 0.0:
                production = 0.0
            assessmentProduction = "-2"
        elif (production < 0.1):
            assessmentProduction = "-1"
        elif (production < 0.5):
            assessmentProduction = "0"
        elif (production < 0.9):
            assessmentProduction = "1"
        else:
            assessmentProduction = "2"
        if (consumption < 10.0):
            aClient.publish ("/inkplate/in/power", f"{day}@{consumption:.3f}@{assessmentConsumption}@{production:.3f}@{assessmentProduction}", qos=1, retain=True)
        else:
            aClient.publish ("/inkplate/in/power", f"{day}@{consumption:.2f}@{assessmentConsumption}@{production:.3f}@{assessmentProduction}", qos=1, retain=True)

    def publishMOTD():
        def getEvents(my_principal, calname, calid, offset, duration):

            calendars = my_principal.calendars()

            my_calendar = my_principal.calendar(name=calname, cal_id=calid)

            events_fetched = my_calendar.date_search(
                start=date.today() + timedelta(days=offset), end=date.today() + timedelta(days=offset + duration), expand=True)

            results = []

            for e in events_fetched:
                cal = icalendar.Calendar.from_ical(e._get_data())
                ev = cal.walk("VEVENT")[0]

                no_time = False
                date_override = False
                time = ""

                try:
                    # RDATE not handled yet!
                    rule = ev["RRULE"]
                    # FREQ:YEARLY BYMONTH:<int> BYMONTHDAY:<int>
                    # FREQ:WEEKLY BYDAY:<char2>
                    try:
                        freq = rule["FREQ"] # req! SECONDLY, MINUTELY, HOURLY, DAILY, WEEKLY, MONTHLY, YEARLY
                        # INTERVAL: <digit> factor for FREQ
                    except KeyError:
                        pass
                    if "WEEKLY" in freq:
                        try:
                            byday = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'].index(rule["BYDAY"][0])
                            startDayOfWeek = (date.today() + timedelta(days=offset)).isoweekday()
                            if byday < startDayOfWeek:
                                byday += 7
                            calcday = date.today() + timedelta(days=offset + byday - startDayOfWeek)
                            time = calcday.strftime ("%d.%m.")
                            date_override = True
                            # or BYSECOND, BYMINUTE, BYHOUR (CSL, comma-separated list)
                            # BYDAY (SU, MO, TU, WE, TH, FR, SA) (CSL), +-<integer>: first or last of ...
                            # BYMONTHDAY CSL of days of month, -<integer> last of ...
                            # BYYEARDAY CSL of days of year, -<integer> last of ...
                            # BYWEEKNO CSL of weeks of year, -<integer> last of ...
                            # BYMONTH CSL of months (1..12)
                            # WKST: first work way of week (MO, TU, ... SU)
                        except KeyError:
                            pass
                    elif "YEARLY" in freq:
                        try:
                            print ("yearly")
                            bymonth = rule["BYMONTH"]
                            bymonthday = rule["BYMONTHDAY"]
                            calcday = datetime(year=date.today().year, month=bymonth[0], day=bymonthday[0]);
                            time = calcday.strftime ("%d.%m.")
                            date_override = True
                            no_time = True
                        except KeyError:
                            pass
                    else:
                        time = "<????>"
                        date_override = True
                except KeyError:
                    pass
                #vPeriod: start, end, by_duration, duration
                #vRecur: ?! RRULE
                #vGeo: latitude, longitude
                #vUTCOffset: td

                try:
                    if ev["DURATION"].dt >= timedelta (days=1):
                        no_time = True
                except KeyError:
                    pass

                try:
                    if not date_override:
                        time = ev["DTSTART"].dt.strftime ("%d.%m.")
                    if not no_time:
                        time += ev["DTSTART"].dt.strftime (" %H:%M")
                except KeyError:
                    pass
                try:
                    if not no_time:
                        time += "-" + ev["DTEND"].dt.strftime ("%H:%M")
                except KeyError:
                    pass

                summary = ""
                try:
                    summary = ev["DESCRIPTION"].to_ical().decode("utf-8")
                except KeyError:
                    pass
                try:
                    summary = ev["SUMMARY"].to_ical().decode("utf-8")
                except KeyError:
                    pass
                if len(time) > 0:
                    results += [time + ": " + summary]
                else:
                    results += [summary]

            results.sort()
            return results

        client = caldav.DAVClient(url=url, username=username, password=password)
        my_principal = client.principal()

        results = []
        results += getEvents (my_principal, "Müllabfuhr", "4f7cdade-64f0-9d35-ae78-4bd84ec8d89b", +1, 1)   # tomorrow
        results += getEvents (my_principal, "Geburtstage", "3b626971-7de3-f82a-1899-8fe2d85c04e1", 0, 1)   # today
        line1 = ""
        line2 = ""
        print (results)
        if len(results) == 1:
            line1 = results[0]
        elif len(results) == 2:
            line1 = results[0]
            line2 = results[1]
        elif len(results) == 3:
            line1 = results[0] + "   /   " + results[1]
            line2 = results[2]
        elif len(results) == 4:
            line1 = results[0] + "   /   " + results[1]
            line2 = results[2] + "   /   " + results[3]
        elif len(results) > 4:
            line1 = results[0] + "   /   " + results[1]
            line2 = results[2] + "   /   ... weitere ..."

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


def pictureUpdate():
    try:
        image = Image.new('1', (800, 386))
        humidity = Image.open("/tmp/humidity.gif").convert(mode = "1", dither=Image.NONE)
        image.paste(humidity, (383, 0))
        temperature = Image.open("/tmp/temperature.gif").convert(mode = "1", dither=Image.NONE)
        image.paste(temperature, (-17, 0))
        image.save("/sharedfolders/inkplate/content-1.bmp")

        image = Image.new('1', (800, 386))
        battery = Image.open("/tmp/battery.gif").convert("1", dither=Image.NONE)
        image.paste(battery, (383, 0))
        pressure = Image.open("/tmp/pressure.gif").convert("1", dither=Image.NONE)
        image.paste(pressure, (-17, 0))
        image.save("/sharedfolders/inkplate/content-11.bmp")

        image = Image.new('1', (800, 386))
        power = Image.open("/tmp/allday.png")
        width, height = power.size
        for x in range(width):
            for y in range(height):
                r, g, b = power[x, y]
                if g > 10 and r < 245:
                    power[x, y] = (0, 255, 0)
        image.paste(power.convert("1", dither=Image.NONE), (0, -29))
        image.save("/sharedfolders/inkplate/content-3.bmp")
    except:
        pass


if __name__ == '__main__':
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("mediaberry")

    fullUpdate(client)
    pictureUpdate()

    send_time = TimeThread()
    send_time.start()

    client.loop_forever()
