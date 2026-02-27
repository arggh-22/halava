from fastapi import HTTPException, Header, Depends
from typing import Optional
import hmac
import hashlib
import urllib.parse
import json
import os
from config import BOT_TOKEN

async def get_current_user(authorization: Optional[str] = Header(None)) -> int:
    """
    Validates Telegram WebApp initData and returns the user_id.
    Expected Header: Authorization: tma <initData>
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    
    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0] != "tma":
        raise HTTPException(status_code=401, detail="Invalid Authorization header format. Expected 'tma <initData>'")
    
    init_data = parts[1]
    
    if not validate_init_data(init_data, BOT_TOKEN):
         raise HTTPException(status_code=403, detail="Invalid initData signature")

    try:
        # Extract user_id from init_data
        parsed_data = urllib.parse.parse_qs(init_data)
        user_json = parsed_data.get('user', [None])[0]
        
        if not user_json:
             raise HTTPException(status_code=400, detail="User data missing in initData")
             
        user_data = json.loads(user_json)
        return int(user_data['id'])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse user data: {str(e)}")

def validate_init_data(init_data: str, bot_token: str) -> bool:
    """
    Validates the initData using HMAC-SHA256.
    """
    try:
        parsed_data = urllib.parse.parse_qs(init_data)
        
        hash_value = parsed_data.get('hash', [None])[0]
        if not hash_value:
            return False
        
        # Remove hash from data to validate
        data_check_arr = []
        for key, value in parsed_data.items():
            if key != 'hash':
                data_check_arr.append(f"{key}={value[0]}")
        
        data_check_arr.sort()
        data_check_string = "\n".join(data_check_arr)
        
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        return calculated_hash == hash_value
    except Exception:
        return False
