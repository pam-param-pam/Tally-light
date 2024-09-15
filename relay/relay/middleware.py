from channels.middleware import BaseMiddleware


class RoomAuthMiddleware(BaseMiddleware):
    def __init__(self, inner):
        super().__init__(inner)

    async def __call__(self, scope, receive, send):
        try:
            token_key = dict(scope['headers'])[b'sec-websocket-protocol'].decode('utf-8')
        except (ValueError, KeyError):
            token_key = None
        scope['user'] = AnonymousUser() if token_key is None else await get_user(token_key)
        scope['token'] = token_key
        return await super().__call__(scope, receive, send)