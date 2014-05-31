alarmPy
=======

A Google Calendar powered alarm clock

##Requirements
* Python2.7
* A Google account, with a Google calendar api key
* pytz
* pygame
* apiclient
* gflags
* oauth2client


##Usage

```
usage: AlarmPy [-h]
               [-s YYYY-mm-dd HH:MM | -t MM:SS | --tomorrow HH:MM | --timer <offset in minutes>]
               [-p] [-r <comma delim list>]
               [-n desired name [desired name ...]]

optional arguments:
  -h, --help            show this help message and exit
  -s YYYY-mm-dd HH:MM, --setalarm YYYY-mm-dd HH:MM
                        Set an alarm. Format as: YYYY-mm-dd HH:MM, unless -p
                        specified.
  -t MM:SS, --today MM:SS
                        Only takes a time parameter; assumes alarm is for
                        today.
  --tomorrow HH:MM      Specifies an alarm to go off at HH:MM tomorrow.
  --timer <offset in minutes>
                        Specifies an alarm to go off <minutes> from now.
  -p, --precise         Allows alarm times with seconds. e.g. YYYY-mm-dd
                        HH:MM:SS
  -r <comma delim list>, --recurring <comma delim list>
                        Sets a recurring alarm in the specified interval. e.g:
                        fr, sa, su
  -n desired name [desired name ...], --name desired name [desired name ...]
                        Names an alarm. If not specified, the name will be
                        "alarm"


examples:
no arguments starts the alarm server  
python alarmpy.py

set an alarm for 12 minutes from now and name the alarm to "pasta done!!"
python alarmpy.py --timer 12 -n pasta done!!

set an alarm to go off at 13:37 tomorrow
python alarmpy.py --tomorrow 13:37

```
##Known issues
Playing certain mp3 files on linux will cause the whole shebang to crash.  Thanks pygame!
