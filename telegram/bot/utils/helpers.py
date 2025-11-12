from string import ascii_letters, digits
from random import choices

def make_ref_code(length: int = 16) -> str:
    return ''.join(choices(ascii_letters + digits, k=length))

def build_deeplink(bot_username: str, payload: str) -> str:
    username = bot_username[1:] if bot_username.startswith('@') else bot_username
    return f"https://t.me/{username}?start={payload}"