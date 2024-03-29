#!/usr/bin/env python3.11
# This script checks for new releases of specified series from Kavita
# Then it sends a message to Telegram if there are new releases with the cover and description of each release
# It depends on telegram-send, which can be installed with pip3.11 install telegram-send
# It reads the config from ~/.config/checkKavita.conf
# Check the help below for syntax for the config file
# When debugging, you can set debug=1 below, and it will print out a lot of info
# When debugging you need another variable in your configfile for a different telegram-send configfile: telegramconfigDeb
# This is to be able to debug without spamming the production telegram channel.

debug=0

import pickle
import os
import requests
import configparser
from xml.etree import ElementTree
import re
from time import sleep
import shlex
from pathlib import Path

# FUnction to check if the Kavita API is up:
def check_kavita_api():
    global KAVITA_URL, KAVITA_API
    deb("Checking if Kavita API is up")
    url = str(str(KAVITA_URL) + str('api/Opds/') + str(KAVITA_API) )
    deb("URL: " + url)
    try:
        r = requests.post(url)
        if r.status_code == 200:
            deb("Got response 200 from Kavita")
        else:
            print("Error getting response 200 from Kavita")
            print("Response code: ", r.status_code)
            print("Response text: ", r.text)
            exit(1)
    except requests.exceptions.RequestException as e:
        print("Error connecting to Kavita API:", str(e))
        exit(1)

# Check how long the computer has been up
# If it has been up for less than 5 minutes, sleep for 5 minutes
def check_uptime():
    with open('/proc/uptime', 'r') as f:
        uptime_seconds = float(f.readline().split()[0])
        if uptime_seconds < 300:
            deb("Computer has been up for less than 5 minutes, exiting.")
            exit(0)


# Function to print out help:
def printHelp():
    print("Usage: checkKavita.py")
    print("This script checks for new releases of specified series from Kavita")
    print("Then it sends a message to Telegram if there are new releases with the cover and description of each release")
    print("It reads the config from ~/.config/checkKavita.conf")
    print("Example configuration:")
    print("[General]")
    print("picklefile = /path/to/where/you/want/to/save/your/picklefile")
    print("tmpfile = /tmp/checkKavita.jpg ")
    print("telegramconfig = /path/to/your/telegram-send.conf")
    print("")
    print("[Kavita]")
    print("url = https://kavita.your.domain")
    print("api = 1234567890")
    print("")
    print("[series]")
    print("21 = My newspaper")
    print("42 = My magazine")
    print("")
    print("If you want to reset your picklefile, just delete it and run the script again.  ")
    print("All series in your configfile will get set to the latest issue, and will not spamm Telegram.")
    print("Subsequent runs will only send new issues to Telegram.")

# Function to print out info when testing:
def deb(d):
    global debug
    if debug: 
        print("\tDEBUG: ", d)

# Function to read config from the configfile:
def read_config(): 
    global KAVITA_URL, KAVITA_API, series, debug, conf_series, PICKLEFILE, TMPFILE, TELEGRAMCONFIG
    config = configparser.ConfigParser()
    deb("Reading config file")
    try:
        config.read(str(Path.home()) + '/.config/checkKavita.conf')
    except:
        print("Error reading config file from " + str(Path.home()) + '/.config/checkKavita.conf')
        printHelp()
        exit(1)
    try:
        KAVITA_URL=config.get('Kavita', 'url')
        KAVITA_API=config.get('Kavita', 'api')
        PICKLEFILE=config.get('General', 'picklefile')
        TMPFILE=config.get('General', 'tmpfile')
        TELEGRAMCONFIG=config.get('General', 'telegramconfig')
        if debug:
            TELEGRAMCONFIG=config.get('General', 'telegramconfigDeb')
        conf_series=config['series']
        deb("Kavita URL: " + KAVITA_URL)
        deb("Kavita API: " + KAVITA_API)
        deb("Picklefile: " + PICKLEFILE)
        deb("Tmpfile: " + TMPFILE)
        deb("Telegramconfig: " + TELEGRAMCONFIG)
        if debug: 
            deb("Series: ")
            for s,ss in conf_series.items():
                deb( s + " " + ss)
    except:
        print("Your config file misses some sections or variables.")
        printHelp()
        exit(1)

# Function to save the pickle file:
def save_pickle():
    deb("Saving pickle file")
    global series, PICKLEFILE
    with open(PICKLEFILE, 'wb') as f:
        pickle.dump(series, f)

# Function to initialise the series dict if the pickle file is missing:
def initialise_series():
    global series
    deb("Initialising series")
    series = {}

# Function to check if the pickle file exists, and if not, create it:
# If it exists, read it into the series dict
def check_pickle():
    global series,PICKLEFILE
    deb("Checking for pickle file")
    try:
        # check if picklefile exists
        if not os.path.isfile(PICKLEFILE):
            deb("Pickle file not found, creating it")
            initialise_series()
            save_pickle()
        else:
            with open(PICKLEFILE, 'rb') as f:
                deb("Pickle file found, reading it")
                series = pickle.load(f)
    except:
        deb("Pickle not found, creating it")
        initialise_series()
        save_pickle()

# Function to get the latest issue ID from Kavita for a given serieID:
def get_latest_issue_id_from_kavita(serieID):
    global KAVITA_URL, KAVITA_API
    deb("Getting latest issue ID from Kavita for serieID: " + str(serieID))
    url = str(str(KAVITA_URL) + str('api/Opds/') + str(KAVITA_API) + str('/series/') + str(serieID))
    deb("URL: " + url)
    r = requests.get(url)
    if r.status_code == 200:
        deb("Got response 200 from Kavita")
        tree = ElementTree.fromstring(r.content)
        # find the id of the latest <entry>
        for entry in tree.findall('{http://www.w3.org/2005/Atom}entry[last()]'):
            for id in entry.findall('{http://www.w3.org/2005/Atom}id[last()]'):
                deb("Found id: " + id.text)
                return id.text
    else:
        print("Error getting latest issue ID from Kavita for serieID: ", serieID)
        exit(1)

# Function to check if there are new series in the config file compared to the saved picklefile,
# and if so, add them to the pickle file.  Remove any not in the config file
def check_for_new_series_from_config():
    global series, conf_series
    for s in conf_series:
        if s not in series:
            deb("Adding serie: " + s + " to pickle file.")
            series[s] = {}
            series[s]["serie"] = conf_series[s]
            series[s]["siste"] = get_latest_issue_id_from_kavita(s)
    for s in series:
        if s not in conf_series:
            deb("Removing serie: " + s + " from pickle file.")
            del series[s]
    save_pickle()

# Function to get a dict about a given id from the XML-file from Kavita for a given serieID:
def get_dict_about_id(id,tree):
    for child in tree:
        xml_id = child.findall('{http://www.w3.org/2005/Atom}id')
        if xml_id and xml_id[0].text == str(id):
            ret={}
            l=1
            for a in child:
                if a.tag == "{http://www.w3.org/2005/Atom}link":
                    ret["link"+str(l)]=a.attrib['href']
                    l+=1
            ret.update({re.match(r'.*}(.*)', a.tag).groups()[0]: a.text for a in child})
            return ret

# Function to check if there are new issues of a given serieID, and if so, send a message to Telegram:
def check_all_series():
    global KAVITA_URL, KAVITA_API, TMPFILE, series, debug, TELEGRAMCONFIG
    for s in series:
        deb("Checking serie: " + series[s]["serie"])
        newest = get_latest_issue_id_from_kavita(s)
        if newest != series[s]["siste"]:
            deb("New release of " + series[s]["serie"] + " is available.")
            url = str(str(KAVITA_URL) + str('api/Opds/') + str(KAVITA_API) + str('/series/') + str(s))
            r = requests.get(url)
            if r.status_code == 200:
                deb("Got response 200 from Kavita")
                tree = ElementTree.fromstring(r.content)
                ids = []
                # Get all the ids of the new issues
                for entry in tree.findall('{http://www.w3.org/2005/Atom}entry'):
                    if int(entry.findall('{http://www.w3.org/2005/Atom}id')[0].text) > int(series[s]["siste"]):
                        ids.append(entry.findall('{http://www.w3.org/2005/Atom}id')[0].text)
                if debug:
                    for id in ids:
                        deb("New issue ID: " + id)
            else:
                print("Error getting latest issue ID from Kavita for serieID: ", s)
                exit(1)
            # We have new issues, so go through them and inform on Telegram:
            if len(ids) > 0:
                for id in ids:
                    entry=get_dict_about_id(id,tree)
                    name=entry['title']
                    imgURL=entry['link1']
                    summary=entry['summary']
                    deb("Name: " + name)
                    deb("imgURL: " + imgURL)
                    deb("summary: " + summary)
                    print("New release of " + series[s]["serie"] + " is available: " + name + " (" + summary + ")" )
                    # fetch the image to a temp file
                    deb("Fetching image from url: " + shlex.quote(KAVITA_URL + imgURL[1:]))
                    os.system('curl -s --output ' + TMPFILE + " " + shlex.quote(KAVITA_URL + imgURL[1:]))
                    os.system('/usr/local/bin/telegram-send --config ' + TELEGRAMCONFIG + ' --image ' + TMPFILE + ' --caption "' + shlex.quote(name + ' (' + summary + ')') + '"')
                    os.remove(TMPFILE)
                    sleep(5)
            series[s]["siste"] = newest
            save_pickle()
        else:
            deb("No new issue of " + series[s]["serie"] + " available.")

check_uptime()

read_config()
check_pickle()
check_for_new_series_from_config()

check_kavita_api()

# When testing:
# series["21"]["siste"]="25740"
# morgenbladet 6779 13702
# series["6779"]["siste"]="13702"
check_all_series()
