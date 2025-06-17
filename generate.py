# G-20ECB8DC7C31B190:false:3445861433:36:1800/1977591f81b/11/true/240/3445861433/a5b6e6b/0
import random
import time
from datetime import datetime, timezone
from ctypes import c_int32
import json

data_dict = ["" for _ in range(6)]
data_dict[3] = '4'
def get_yq_guid() -> str:
    rnd64 = random.getrandbits(64)
    hex16 = f"{rnd64:016X}"
    return f"G-{hex16}"

# test_data = {"data":[{"num":"286784368762","fc":"100003","sc":0},{"num":"286794654695","fc":"100003","sc":0}],"guid":"","timeZoneOffset":240}
# test_data_len = len(json.dumps(test_data, separators=(',',':')))

def str_to_hex(s: str) -> str:
    return ''.join(format(ord(ch), 'x') for ch in s)

def data_dict_add2(n: int) -> int:
    rnd = random.random()
    value = round(rnd * n)

    hex_str = format(value, 'x')

    data_dict[1] = hex_str
    data_dict[2] = str(len(hex_str))

    return value

def js_hash(s: str, seed: int) -> int:
    h = c_int32(1315423911 ^ (seed << 16)).value
    for ch in reversed(s):
        code = ord(ch)
        left = c_int32(h << 5).value
        right = c_int32(h >> 2).value
        h = c_int32(h ^ (left + code + right)).value
    return abs(h & 0x7FFFFFFF)

def data_dict_add1(string: str, seed: int, save: bool = False) -> None:
    if not isinstance(string, str):
        string = json.dumps(string, separators=(',',':'))
    hashed_js = js_hash(string, seed)
    hex_padded_js_hash = "{:08x}".format(hashed_js)
    if save:
        data_dict[5] = hex_padded_js_hash
        return
    data_dict[4] = hex_padded_js_hash

def formatted_now() -> hex:
    now_ms = int(time.time() * 1000)
    return format(now_ms, 'x')

def get_time_offset() -> str:
    offset_td = datetime.now(timezone.utc).astimezone().utcoffset()
    offset_minutes = -int(offset_td.total_seconds() / 60)
    return str(offset_minutes)

def generate_last_id_hash(cookie: str):
    datadict2value = data_dict_add2(48)
    first_part = f'{cookie}:false:3445861433:{datadict2value}:{datadict2value * 50}' 
    second_part = f'/{formatted_now()}/11/true/{get_time_offset()}/3445861433/a5b6e6b/0'
    return first_part + second_part, datadict2value

def generate_salt(last_id_hash: str, datadict2value: int, test_data: dict) -> str:
    data_dict_add1(test_data, len(json.dumps(test_data, separators=(',',':'))), True)
    data_dict_add1(last_id_hash, datadict2value)
    return "".join(data_dict)

def generate_last_id(test_data: dict):
    cookie = get_yq_guid()
    hash_value, d2value = generate_last_id_hash(cookie)
    salt = generate_salt(hash_value, d2value, test_data)
    return str_to_hex(hash_value[::-1]) + salt, cookie
