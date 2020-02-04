from os import environ, path
from dotenv import load_dotenv
from flask import Flask, request
import requests
import mysql.connector
import re
from datetime import datetime

load_dotenv(".env")

try:
    DEBUG = environ.get("DEBUG")
    DEBUG = int(DEBUG)
except Exception as e:
    DEBUG = 0
if DEBUG == 1:

    def debuglog(log):
        with open("./debug.log", "at") as f:
            f.write(datetime.now().isoformat() + " " + log + "\n")

else:

    def debuglog(log):
        pass


debuglog("STARTUP")

app = Flask(__name__)
webhook_route = "/fb/webhook"

mysql_env = {
    "user": environ.get("MYSQL_USERNAME"),
    "password": environ.get("MYSQL_PASSWORD"),
    # 'host': environ.get("MYSQL_HOST"),
    "database": environ.get("MYSQL_DATABASE"),
}


def enqueue(psid, url, segment):
    """queue requests to db"""
    cnx = mysql.connector.connect(**mysql_env)
    cursor = cnx.cursor()
    insert_command = "INSERT INTO requests \
                      (PSID, URL, SEGMENT) VALUES (%s, %s, %s)"
    insert_values = (psid, url, segment)
    cursor.execute(insert_command, insert_values)
    cnx.commit()
    cursor.close()
    cnx.close()
    debuglog("message queued")
    return


def in_queue(psid):
    """check db for user pending status"""
    cnx = mysql.connector.connect(**mysql_env)
    cursor = cnx.cursor()
    check_command = "SELECT * FROM requests WHERE PSID = {}".format(psid)
    cursor.execute(check_command)
    row = cursor.fetchone()
    result = row is not None
    cursor.close()
    cnx.close()
    debuglog("%s in_queue? %s" % (psid, result))
    return result


def wakeup(*args):
    """wake up request fetcher"""
    debuglog("wakeup")
    pass


# TODO: parallelize
def acknowledge(psid):
    """acknowledge msg with seen status"""
    reply_obj = {"recipient": {"id": psid}, "sender_action": "mark_seen"}
    req = requests.post(
        "https://graph.facebook.com/v2.6/me/messages",
        params={"access_token": environ.get("PAGE_ACCESS_TOKEN")},
        json=reply_obj,
    )
    debuglog("message acknowledged")


@app.route("/")
def landing():
    """root path template"""
    debuglog("homepage")
    return "<pre>200 OK</pre>", 200


@app.route(webhook_route, methods=["GET"])
def verify():
    """verify webhook"""
    debuglog("verification request")
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    reply = request.args.get("hub.challenge")
    if (mode, token) == ("subscribe", environ.get("VERIFY_TOKEN")):
        debuglog("verification passed")
        return reply, 200
    debuglog("verification failed")
    return "<pre>401 UNAUTHORIZED</pre>", 401


@app.route(webhook_route, methods=["POST"])
def listen():
    """handle incoming messages"""
    debuglog("incoming message")
    event = request.get_json()
    if event["object"] == "page":
        for entry in event["entry"]:
            payload = entry["messaging"][0]
            debuglog(str(payload))
            psid = payload["sender"]["id"]
            if "text" in payload["message"].keys():
                if not in_queue(psid):
                    segment, url = 0, "help"
                    message = payload["message"]["text"]
                    args = re.search(r"^ *get +(.+)$", message)
                    if args is not None:
                        param = args.group(1).split(" ")
                        if re.fullmatch(r"\d+", param[0]) is not None:
                            segment = int(param[0])
                            url = "".join(param[1:])
                        else:
                            segment = 1
                            url = "".join(param)
                    enqueue(psid, url, segment)
            acknowledge(psid)
        wakeup()
        return "200 OK", 200
    else:
        return "<pre>400 BAD REQUEST</pre>", 400

