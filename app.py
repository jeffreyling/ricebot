import os
import sys
import json
from datetime import datetime
import urllib2
import re

import requests
from flask import Flask, request

from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class RiceRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True)
    amount = db.Column(db.Float())  # in cups

    def __init__(self, name, amount=0.):
        self.name = name
        self.amount = amount

    def __repr__(self):
        return "({}, {} cups)".format(self.name, self.amount)


def get_user_first_name(sender_id):
    """ Retrieves first name using Graph API """
    request = "https://graph.facebook.com/v2.6/{}?fields=first_name&access_token={}".format(sender_id, os.environ["PAGE_ACCESS_TOKEN"])
    response = urllib2.urlopen(request)
    data = json.load(response)

    return data["first_name"]


@app.route('/', methods=['GET'])
def verify():
    # when the endpoint is registered as a webhook, it must echo back
    # the 'hub.challenge' value it receives in the query arguments
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.challenge"):
        if not request.args.get("hub.verify_token") == os.environ["VERIFY_TOKEN"]:
            return "Verification token mismatch", 403
        return request.args["hub.challenge"], 200

    return "Hello world", 200


@app.route('/', methods=['POST'])
def webhook():

    # endpoint for processing incoming messaging events

    data = request.get_json()
    log(data)  # you may not want to log every incoming message in production, but it's good for testing

    if data["object"] == "page":

        for entry in data["entry"]:
            for messaging_event in entry["messaging"]:

                if messaging_event.get("message"):  # someone sent us a message

                    sender_id = messaging_event["sender"]["id"]        # the facebook ID of the person sending you the message
                    recipient_id = messaging_event["recipient"]["id"]  # the recipient's ID, which should be your page's facebook ID

                    first_name = get_user_first_name(sender_id)  # poster's first name


                    if "text" in messaging_event["message"]:  # prevent emojis from crashing us
                        message_text = messaging_event["message"]["text"]  # the message's text
                        if message_text == "help":
                            send_message(sender_id,
                            """Send \"rice 1.5\" to post 1.5 cups of rice.\n
                                Send \"clear\" to clear your request.\n
                                Send \"show\" to see who has requested rice so far.\n
                                You can clear your last request with a new one too.""")
                        elif re.match("rice \d+(\.\d+)?", message_text):
                            amt = float(message_text.strip().split()[-1])
                            prev_req = RiceRequest.query.filter_by(name=first_name).first()
                            if prev_req:
                                db.session.delete(prev_req)
                                db.session.commit()
                                rice_req = RiceRequest(first_name, amt)
                                db.session.add(rice_req)
                                db.session.commit()
                                send_message(sender_id, "new request: {} cups".format(amt))
                            else:
                                rice_req = RiceRequest(first_name, amt)
                                db.session.add(rice_req)
                                db.session.commit()
                                send_message(sender_id, "got it! {} cups".format(amt))

                        elif message_text == "clear":
                            rice_req = RiceRequest.query.filter_by(name=asdf).first()
                            if rice_req:
                                db.session.delete(rice_req)
                                db.session.commit()
                                send_message(sender_id, "your request was cleared")
                            else:
                                send_message(sender_id, "you didn't request rice today")
                        elif message_text == "show":
                            send_message(sender_id, "these people want rice: {}".format(RiceRequest.query.all()))
                        else:
                            send_message(sender_id, "I don't understand")

                if messaging_event.get("delivery"):  # delivery confirmation
                    pass

                if messaging_event.get("optin"):  # optin confirmation
                    pass

                if messaging_event.get("postback"):  # user clicked/tapped "postback" button in earlier message
                    pass

    return "ok", 200


def send_message(recipient_id, message_text):

    log("sending message to {recipient}: {text}".format(recipient=recipient_id, text=message_text))

    params = {
        "access_token": os.environ["PAGE_ACCESS_TOKEN"]
    }
    headers = {
        "Content-Type": "application/json"
    }
    data = json.dumps({
        "recipient": {
            "id": recipient_id
        },
        "message": {
            "text": message_text
        }
    })
    r = requests.post("https://graph.facebook.com/v2.6/me/messages", params=params, headers=headers, data=data)
    if r.status_code != 200:
        log(r.status_code)
        log(r.text)


def log(msg, *args, **kwargs):  # simple wrapper for logging to stdout on heroku
    try:
        if type(msg) is dict:
            msg = json.dumps(msg)
        else:
            msg = unicode(msg).format(*args, **kwargs)
        print u"{}: {}".format(datetime.now(), msg)
    except UnicodeEncodeError:
        pass  # squash logging errors in case of non-ascii text
    sys.stdout.flush()


if __name__ == '__main__':
    app.run(debug=True)
