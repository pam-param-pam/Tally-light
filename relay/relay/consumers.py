import json
import threading
from json import JSONDecodeError

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from django.core.cache import cache


class TallyConsumer(WebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.authenticated = False
        self.auth_timer = None
        self.tally_number = None
        self.room_id = None

    def connect(self):
        print("opening tally consumer")
        self.accept()
        # Start a timer for 5 seconds to close the connection if not authenticated
        self.auth_timer = threading.Timer(5, self.close_if_not_authenticated)
        self.auth_timer.start()

    def close_if_not_authenticated(self):
        # This function is called after 15 seconds after accepting the connection
        if not self.authenticated:
            print("close tally 1")
            self.close(code=1000, reason="No auth provided")

    def disconnect(self, close_code):
        print("tally disconnect")
        async_to_sync(self.channel_layer.group_discard)("tally", self.channel_name)
        async_to_sync(self.channel_layer.group_send)("atem", {
            "type": "send_event_to_atem",
            "room_id": self.room_id,
            "event_data": json.dumps({"op": 7, "t": self.tally_number, "d": "Tally disconnected!"})
        })

    def receive(self, text_data=None, bytes_data=None):
        print(f"tally received {text_data}")
        try:
            message = json.loads(text_data)
            op_code = message["op"]
            tally = message["t"]
            data = message["d"]

            # first message must be auth room ID
            if not self.authenticated and op_code != 1:
                print("close tally 2")
                self.close()

            if op_code == 1:  # IDENTIFY EVENT, sent from tally to relay server
                self.tally_number = tally
                self.room_id = data['rId']
                async_to_sync(self.channel_layer.group_add)("tally", self.channel_name)

                # Send EVENT informing ATEM of a new tally connected
                async_to_sync(self.channel_layer.group_send)("atem", {
                    "type": "send_event_to_atem",
                    "room_id": self.room_id,
                    "event_data": json.dumps({"op": 5, "t": self.tally_number, "d": "New tally connected!"})
                })
                self.authenticated = True
                print(f"TALLY AUTH successful tally_number={self.tally_number} room_id={self.room_id}")

            # forward any other event to atem
            else:
                async_to_sync(self.channel_layer.group_send)("atem", {
                    "type": "send_event_to_atem",
                    "room_id": self.room_id,
                    "event_data": text_data
                })

        except (KeyError, JSONDecodeError):

            # first message must be a valid IDENTIFY event
            if not self.authenticated:
                print("close tally 3")
                self.close()

    def send_event_to_tally(self, event):
        if event["room_id"] != self.room_id:
            return
        event = json.loads(event["event_data"])
        tally_number = event["t"]
        if tally_number == 0 or tally_number == self.tally_number:
            self.send(json.dumps(event))


class AtemConsumer(WebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.room_id = None
        self.authenticated = False

    def connect(self):
        try:
            print("opening atem")
            self.room_id = dict(self.scope['headers'])[b'room-id'].decode('utf-8')

            # allow only 1 atem per room_id
            print(self.get_consumer_count(self.room_id))
            if self.get_consumer_count(self.room_id) != 0:
                print("close atem 1")
                self.close(reason="There is already atem listener connected in this room ID")
            else:
                self.accept()
                async_to_sync(self.channel_layer.group_add)("atem", self.channel_name)
                self.authenticated = True
                self.increment_consumer_count()
                print(f"ATEM AUTH successful room_id={self.room_id}")

        except (KeyError, ValueError):
            print("close atem 2")

            self.close()

    def disconnect(self, close_code):
        print("disconnect atem 1")
        async_to_sync(self.channel_layer.group_discard)("atem", self.channel_name)
        if self.authenticated:
            print("disconnect atem 2")
            self.decrement_consumer_count()
            async_to_sync(self.channel_layer.group_send)("tally", {
                "type": "send_event_to_tally",
                "room_id": self.room_id,
                "event_data": json.dumps({"op": 8, "t": 0, "d": ":("})
            })

    def receive(self, text_data=None, bytes_data=None):
        print(f"atem received {text_data}")

        # forward everything to tally consumer
        async_to_sync(self.channel_layer.group_send)("tally", {
            "type": "send_event_to_tally",
            "room_id": self.room_id,
            "event_data": text_data,
        })

    def send_event_to_atem(self, event):
        print(f"atem received from tally {event}")
        if event["room_id"] != self.room_id:
            return
        print("sending event to atem")
        print(event)
        self.send((event["event_data"]))

    def increment_consumer_count(self):
        key = f'{self.room_id}_count'
        count = cache.get(key, 0)
        cache.set(key, count + 1)

    def decrement_consumer_count(self):
        key = f'{self.room_id}_count'
        count = cache.get(key, 0)
        cache.set(key, max(0, count - 1))  # Ensure count doesn't go below 0

    def get_consumer_count(self, room_id):
        # Retrieve the count of consumers in the room from cache
        return cache.get(f'{room_id}_count', 0)
