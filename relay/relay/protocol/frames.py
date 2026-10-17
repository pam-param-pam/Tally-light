from enum import Enum


MAX_FRAME_BYTES = 2048


class FrameType(str, Enum):
    HELLO = "hello"
    WELCOME = "welcome"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"
    ATEM_STATE = "atem.state"
    SETTINGS_SET = "settings.set"
    SETTINGS_RESULT = "settings.result"
