#!/usr/bin/env python
# -*- coding: utf-8 -*- 

# Requires google api account, google stuff: gflags, ouath2client, apiclient
# pytz, pygame
# TODO:  replace pygame with other, cross platform audio library
import ConfigParser
import sys
import argparse
import httplib2
import dateutil.parser
import datetime
import pytz
import pygame
import os
import random
import Queue
try:
    import RPi.GPIO as GPIO
    button_available = True
except ImportError:
    button_available = False
from Queue import PriorityQueue
from time import sleep
import apiclient
import gflags
from apiclient.discovery import build
from oauth2client.file import Storage
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.tools import run

class AlarmError(Exception):
    pass

class AlarmPy(object):
    """song_dir is the directory holding the mp3 files you want to pull
    alarm tunes from.
    interval is the interval in seconds with which we poll Google Calendar for any
    changes, e.g. new or removed alarms.
    """

    def __init__(self, api_id, api_secret, api_scope, 
            timezone, calendar_id, song_dir='songs', interval=45):
        self.tz = pytz.timezone(timezone)
        self.now = datetime.datetime.now
        utc = self.now(self.tz).strftime('%z')
        self.utc = utc[0:3] + ":" + utc[3:]
        self.alarms = None
        self.debug = True

        if os.path.isdir(song_dir):
            self.song_dir = song_dir
        else:
            raise AlarmException("Song directory doesn't exist.")
        self.calendar_id = calendar_id
        self.interval = datetime.timedelta(seconds=interval) 
        if button_available:
            # setup the gpio button
            self.button_pin = 17
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.button_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        pygame.mixer.init()
        self.gcal_init(api_id, api_secret, api_scope)
        self.update_alarms()

    def gcal_init(self, client_id, client_secret, api_scope):
        """Initialize the service object, through which we
        interact with the Google calendar storing our alarms.
        """
        print "Initializing connection with Google Calendar..."
        FLAGS = gflags.FLAGS

        # Set up a Flow object to be used if we need to authenticate. 
        # The client_id and client_secret are copied from the 
        # API Access tab on the Google APIs Console.
        # https://code.google.com/apis/console/
        self.FLOW = OAuth2WebServerFlow(
                client_id = client_id,
                client_secret = client_secret,
                scope = api_scope)

        # Credentials will get written back to a file.
        self.storage = Storage('calendar.dat')
        self.update_gcal_tokens()
        print "Done!"

    def update_gcal_tokens(self):
        """Update access token if token_expiry is due."""
        # update last_update
        self.last_update = self.now(self.tz)
        credentials = self.storage.get()
        if credentials is None or credentials.invalid == True:
            credentials = run(self.FLOW, self.storage)

        # Create an httplib2.Http object to handle our HTTP requests
        # and authorize it with our good Credentials.
        http = httplib2.Http()
        http = credentials.authorize(http)

        # Build a service object for interacting with the API. Visit
        # the google APIs Console to get a developerKey for your own 
        # application.
        self.service = build(serviceName='calendar',
                version='v3', http=http)

    def listen(self):
        """Listen for alarms and trigger them if necessary."""
        print "Listening after alarms..."
        while True:
            # wait in get_alarm until we have an alarm
            self.get_alarm()

            # loop until an alarm goes off
            self.start = self.now()
            while self.now(self.tz) < self.alarm:
                self.check_alarms()
                # sleep to prevent eating the cpu
                sleep(1)

            print "[{}]: Alarm went off!".format(self.now(self.tz))
            self.play_some_beats()
            self.purge_alarms()

    def update_end(self):
        """Update the right endpoint of the update interval."""
        # used to tell google how far into the future you want to
        # check your alarms
        self.end = self.now() + datetime.timedelta(days=365)
        self.end = self.end.strftime("%Y-%m-%dT%H:%M:%S%z") + self.utc
    
    def get_alarm(self):
        """Retrieve the earliest alarm.
        If we don't have any alarms we wait until we get one.
        """
        while True:
            try:
                self.update_alarms()
                # if we don't have any alarms, we wait <interval> seconds and
                # then attempt to get alarms again
                self.alarm = self.alarms.get(timeout=self.interval.total_seconds())
                self.alarms.put(self.alarm)
                print self.alarm
                return 
            except Queue.Empty:
                # Block until we have an alarm
                pass

    def check_alarms(self):
        """Check if the newest alarm is the one we're monitoring. 
        If it isn't then update self.alarm to reflect the newest one.
        """

        if self.now() - self.start >= self.interval:
            self.get_alarm()
            self.start = self.now()

    def update_alarms(self):
        """Update self.alarms with new alarms.
        Range is from self.now(self.tz) until self.end.
        """

        count = 0
        interval = datetime.timedelta(days=1)
        # while True allows us to recover from 503 backend errors
        while True:
            try:
                # make sure our access token is valid
                # only update our token if it has been more than a day
                if self.last_update - self.now(self.tz) > interval:
                    self.update_gcal_tokens()
                # update the the right endpoint of the interval, we pull events from [now, end]
                self.update_end()

                self.alarms = PriorityQueue()
                # get all events from self.now until self.end
                cal_events = self.service.events().list(
                        calendarId=self.calendar_id,
                        timeMin=self.now(self.tz).strftime('%Y-%m-%dT%H:%M:%S.%f%z'),
                        timeMax=self.end
                        ).execute()
                break
            except:
                e = sys.exc_info()[0]
                count += 1
                if self.debug:
                    print "recovering from backend error", count
                    print e
                self.update_gcal_tokens()
                sleep(1)

        # grab the starting times for all events in cal_events
        for event in cal_events.get('items', []):
            # don't grab events without starting times 
            if u"dateTime" in event["start"]:
                datetime_string = event['start'][u'dateTime']
                datetime_object = dateutil.parser.parse(datetime_string)
                # only store the times that start after the current time
                if datetime_object > self.now(self.tz):
                    self.alarms.put(datetime_object)

    def set_alarm(self, datetime_obj, name='alarm', days=None):
        """Set new alarms in self.calendar."""

        # parse user string
        dt_object = dateutil.parser.parse(datetime_obj)
        if dt_object < self.now(self.tz):
            raise AlarmError("Invalid input. Alarm is in the past.")
        valid_days = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU']
        if days:
            # remove any whitespaces
            days = "".join(days.split()) 
            for day in days.upper().split(','):
                # check input
                if day not in valid_days:
                    raise AlarmException(
                            "Recurrence range invalid.\nFormat as: {}".format(
                                ", ".join(valid_days).lower()))
            recurrence_rule = ['RRULE:FREQ=DAILY;BYDAY=' + days.upper()]
        else:
            recurrence_rule = [] 

        event = {
                'summary': name,
                'start': {
                    'dateTime': datetime_obj,
                    'timeZone': self.tz.zone
                    },
                'end' : {
                    'dateTime': datetime_obj,
                    'timeZone': self.tz.zone
                    },
                'recurrence': recurrence_rule
                }
        # fire away the event to Google!
        self.service.events().insert(
                calendarId=self.calendar_id,
                body=event).execute()

    def purge_alarms(self):
        """Go through self.alarms removing alarms in the past."""
        # go through the alarms, removing expired ones
        while not self.alarms.empty():
            # remove expired alarms
            self.alarm = self.alarms.get()
            if self.alarm < self.now(self.tz):
                print "Removing: {}".format(self.alarm)
            # if the alarm hasn't expired, put it back
            else:
                self.alarms.put(self.alarm)
                break

    def play_some_beats(self):
        """Play some funky alarm beats.

        Beats are randomly selected from self.song_dir, and looped
        until the alarm is silenced, or until 5 minutes have passed.
        """

        # randomly choose a song from the song dir
        # do this every time we run an alarm

        self.extensions = ("mp3", "ogg", "wav" )
        # only grab the files that we can listen to
        songs = [f for f in os.listdir(self.song_dir) if
                f.lower().endswith(self.extensions)]
        song = songs[random.randint(0, len(songs)-1)]
        print song
        start = self.now()
        duration = datetime.timedelta(minutes=5)
        pygame.mixer.music.load(os.path.join(self.song_dir, song))
        pygame.mixer.music.play(-1)
        clock = pygame.time.Clock()

        while pygame.mixer.music.get_busy():
            # check if playback has finished
            clock.tick(50)
            if button_available:
                if not GPIO.input(self.button_pin) or self.now() - start > duration:
                    pygame.mixer.music.fadeout(250)
            else:
                try:
                    if self.now() - start > duration:
                        raise KeyboardInterrupt
                except KeyboardInterrupt:
                    pygame.mixer.music.fadeout(250)
        print "You stopped the music!"

    def exit(self):
        pygame.mixer.quit()

parser = argparse.ArgumentParser("AlarmPy")
group = parser.add_mutually_exclusive_group()
group.add_argument("-s", "--setalarm", nargs=2, metavar=("YYYY-mm-dd","HH:MM"),
        help="Set an alarm. Format as: YYYY-mm-dd HH:MM, unless -p specified.")
group.add_argument("-t", "--today", nargs=1, metavar="MM:SS", 
        help="Only takes a time parameter; assumes alarm is for today.")
group.add_argument("--tomorrow", nargs=1, metavar="HH:MM",
        help="Specifies an alarm to go off at HH:MM tomorrow.")
group.add_argument("--timer", nargs=1, metavar="<offset in minutes>",
        type=int, help="Specifies an alarm to go off <minutes> from now.")
parser.add_argument("-p", "--precise", action="store_true", 
        help="Allows alarm times with seconds. e.g. YYYY-mm-dd HH:MM:SS")
parser.add_argument("-r", "--recurring", metavar="<comma delim list>",
        help="Sets a recurring alarm in the specified interval. e.g: fr, sa, su")
parser.add_argument("-n", "--name", nargs="+", metavar="desired name",
        help="Names an alarm. If not specified, the name will be \"alarm\"")

def main():
    args = parser.parse_args()
    config = ConfigParser.ConfigParser()
    try:
        with open("settings.cfg") as f:
            config.readfp(f)
    except (ConfigParser.NoSectionError, 
            ConfigParser.NoOptionError) as e:
        print "Invalid config file: "
        print e
        print "Exiting."
        sys.exit(1)

    # Grabs all the settings in settings.cfg and feeds them to AlarmPy's init
    try:
        alarm = AlarmPy(**dict(config.items("Settings")))
    except TypeError as e:
        print "Error: settings.cfg is improperly formatted."
        print "Error message: {}".format(sys.exc_info()[1])
        sys.exit(1)
    except pytz.exceptions.UnknownTimeZoneError as e:
        print "Unknown timezone: "
        print "timezone = " + str(e).replace("'", "")
        sys.exit(1)
    except:
        print "uncaught exception"
        print sys.exc_info()
        sys.exit(1)

    if args.setalarm or args.today or args.tomorrow or args.timer:
        if args.name:
            name = " ".join(args.name)
        else:
            name = "alarm"
        error_msg = "Invalid input.\nPlease format as: YYYY-MM-DD HH:MM"
        # if today, prepend today's date and format dtstring
        if args.timer:
            error_msg ="Invalid input.\nPlease input the offset in minutes only."
            offset = datetime.timedelta(minutes=args.timer[0])
            dtobj = alarm.now(alarm.tz) + offset
            dtstring = dtobj.strftime("%Y-%m-%dT%H:%M:%S")
        elif args.today:
            error_msg = "Invalid input.\nPlease format as: HH:MM"
            date = alarm.now(alarm.tz).strftime('%Y-%m-%dT')
            dtstring = date + args.today[0]
        elif args.tomorrow:
            error_msg = "Invalid input.\nPlease format as: HH:MM"
            date = alarm.now(alarm.tz) + datetime.timedelta(days=1)
            dtstring = date.strftime('%Y-%m-%dT') + args.tomorrow[0]
        else:
            # join date and time with T inbetween
            dtstring = "T".join(args.setalarm)

        if args.precise: 
            error_msg += ":SS"
        elif args.timer:
            # we've already formatted the seconds for the timer
            pass
        else:
            seconds =":00"
            dtstring += seconds
        # get the user input, format it correctly and cat with utc offset
        dtstring = "{}{}".format(dtstring, alarm.utc)
        print dtstring
        try: 
            if args.recurring:
                alarm.set_alarm(dtstring, name=name, days=args.recurring)
            else:
                alarm.set_alarm(dtstring, name=name)
        except (ValueError, apiclient.errors.HttpError) as e:
            print "Error: " + str(e).capitalize()
            print error_msg
            sys.exit(1)
        except:
            print "{}\n{}".format(*sys.exc_info()[0:2])
            sys.exit(1)
    else:
        wait_time = 60
        while True:
            try:
                alarm.listen()
            except (Exception) as e:
                print "Connection Error: " + str(e).capitalize()
                print "Reattempting to connection in {} seconds.".format(wait_time)
                sleep(wait_time)

if __name__ == '__main__':
    main()
