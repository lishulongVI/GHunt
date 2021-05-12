#!/usr/bin/env python3

import json
import sys
import os
from datetime import datetime
from io import BytesIO
from os.path import isfile
from pathlib import Path
from pprint import pprint

import httpx
from PIL import Image
from geopy.geocoders import Nominatim

import config
from lib.banner import banner
import lib.gmaps as gmaps
import lib.youtube as ytb
from lib.photos import gpics
from lib.utils import *
import lib.calendar as gcalendar


def user_extract(user, data, client, internal_auth, internal_token, cookies):
    res = {}
    gaiaID = user["personId"][0]
    email = user["lookupId"]
    infos = data["people"][gaiaID]

    # get name
    name = get_account_name(client, gaiaID, internal_auth, internal_token, cookies, config)
    if name:
        res['user_name'] = name
    else:
        if "name" not in infos:
            print("[-] Couldn't find name")
        else:
            for i in range(len(infos["name"])):
                if 'displayName' in infos['name'][i].keys():
                    name = infos["name"][i]["displayName"]
                    res['user_name'] = name

    # profile picture
    profile_pic_link = infos["photo"][0]["url"]
    req = client.get(profile_pic_link)

    profile_pic_img = Image.open(BytesIO(req.content))
    profile_pic_hash = image_hash(profile_pic_img)
    is_default_profile_pic = detect_default_profile_pic(profile_pic_hash)
    # 判断是否是默认头像
    res['is_default_profile_pic'] = is_default_profile_pic
    res['profile_imag_url'] = profile_pic_link

    # last edit
    try:
        timestamp = int(infos["metadata"]["lastUpdateTimeMicros"][:-3])
        # last_edit = datetime.utcfromtimestamp(timestamp).strftime("%Y/%m/%d %H:%M:%S (UTC)")
        res['last_profile_update_time'] = datetime.fromtimestamp(timestamp)
        # print(f"\nLast profile edit : {last_edit}")
    except KeyError:
        res['last_profile_update_time'] = None
    res['google_id'] = gaiaID

    # is bot?
    # profile_pic = infos["photo"][0]["url"]
    # res['hangout_profile_image_url'] = profile_pic
    if "extendedData" in infos:
        isBot = infos["extendedData"]["hangoutsExtendedData"]["isBot"]
        if isBot:
            res['is_hangout_bot'] = True
        else:
            res['is_hangout_bot'] = False
    else:
        res['is_hangout_bot'] = None

    # decide to check YouTube
    ytb_hunt = False
    try:
        services = [x["appType"].lower() if x["appType"].lower() != "babel" else "hangouts" for x in
                    infos["inAppReachability"]]
        if name and (config.ytb_hunt_always or "youtube" in services):
            ytb_hunt = True
        res['activated_google_services'] = [x.capitalize() for x in services]

    except KeyError:
        ytb_hunt = True
        res['activated_google_services'] = []

    # check YouTube
    youtube = {
        'channel': [],
        'confidence': None,
        'possible_user_names': []
    }
    if name and ytb_hunt:
        data = ytb.get_channels(client, name, config.data_path,
                                config.gdocs_public_doc)
        if not data:
            pass
        else:
            confidence, channels = ytb.get_confidence(data, name, profile_pic_hash)
            youtube['confidence'] = confidence

            if confidence:
                for channel in channels:
                    youtube['channel'].append({
                        'name': channel['name'],
                        'profile_url': channel['profile_url'],
                    })
                possible_usernames = ytb.extract_usernames(channels)
                if possible_usernames:
                    youtube['possible_user_names'] = possible_usernames

    res['youtube'] = youtube

    # TODO: return gpics function output here
    # gpics(gaiaID, client, cookies, config.headers, config.regexs["albums"], config.regexs["photos"],
    #      config.headless)

    # reviews
    reviews = gmaps.scrape(gaiaID, client, cookies, config, config.headers, config.regexs["review_loc_by_id"],
                           config.headless)
    maps = {
        'confidence': None,
        'location_names': []
    }
    if reviews:
        confidence, locations = gmaps.get_confidence(reviews, config.gmaps_radius)
        loc_names = []
        for loc in locations:
            loc_names.append(
                f"{loc['avg']['town']},{loc['avg']['country']}"
            )
        loc_names = set(loc_names)  # delete duplicates
        maps['loc_names'] = list(loc_names)

    res['maps'] = maps

    # Google Calendar
    calendar_response = gcalendar.fetch(email, client, config)
    res['calendar'] = calendar_response if calendar_response else {"status": False, "events": []}
    return res


def email_hunt(email):
    """
    {
        "email": "xxx@gmail.com",
        "matches": [{
            "user_name": "lsss",
            "profile_imag_url": "",
            "last_profile_update_time": "2021-05-11 22:39:36.727355",
            "google_id": 107640112940428892434,
            "is_default_profile_pic": True,
            "is_hangout_bot": null,
            "activated_google_services": [],
            "youtube": {
                "channel": [],
                "confidence": null,
                "possible_user_names": []
            },
            "maps": {
                "confidence": null,
                "location_names": []
            },
            "calendar": [{
                "title": "title",
                "start_utc_dt": "2021-05-11 22:39:36.727359",
                "duration": "xxxxx"
            }]
        }]
    }
    :param email:
    :return:
    """
    banner()
    res = dict(email=email)
    if not email:
        raise Exception("Please give a valid email.\nExample : larry@google.com")

    if not isfile(config.data_path):
        raise Exception("Please generate cookies and tokens first, with the check_and_gen.py script.")

    with open(config.data_path, 'r') as f:
        out = json.loads(f.read())
        hangouts_auth = out["hangouts_auth"]
        hangouts_token = out["keys"]["hangouts"]
        internal_auth = out["internal_auth"]
        internal_token = out["keys"]["internal"]
        cookies = out["cookies"]

    client = httpx.Client(cookies=cookies, headers=config.headers)

    data = is_email_google_account(client, hangouts_auth, cookies, email,
                                   hangouts_token)

    res['matches'] = []
    for user in data["matches"]:
        u = user_extract(user, data, client, internal_auth, internal_token, cookies)
        res['matches'].append(u)
    return res
