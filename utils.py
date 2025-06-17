import tkinter as tk
import asyncio
import random
import configparser
from typing import Optional, List, Dict, Any

from tkinter import filedialog
from logger import *

class Utils:
    def choose_txt_file(self, file_annotation: str) -> str:
        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.askopenfilename(
            title=file_annotation, 
            filetypes=[('txt file', '*.txt')]
        )
        return file_path
    
    def get_random_proxy(self, proxy_path: str) -> Optional[str]:
        if not proxy_path:
            return None
            
        try:
            with open(proxy_path, "r", encoding="utf-8") as stream:
                proxies = [p.strip() for p in stream.readlines() if p.strip()]
                if not proxies:
                    return None
                    
                proxy = random.choice(proxies)
                
                # Validate and format proxy if needed
                if '://' not in proxy:
                    # Assume http if no protocol specified
                    proxy = f"http://{proxy}"
                
                # Basic proxy validation
                try:
                    splited = proxy.split(':', maxsplit=5)
                    if len(splited) >= 3:
                        protocol = splited[0]
                        if protocol not in ['http', 'https']:
                            logger.warning(f"Unsupported proxy protocol: {protocol}, using as-is")
                        return proxy
                    else:
                        logger.warning(f"Invalid proxy format: {proxy}")
                        return proxy
                except Exception as parse_error:
                    logger.warning(f"Error parsing proxy {proxy}: {parse_error}, using as-is")
                    return proxy
                    
        except Exception as e:
            logger.error(f"Error getting proxy: {str(e)}")
            return None
    
    def parse_17track_response(self, json_data: Dict, track_numbers: list) -> Optional[List]:
        tracks = []
        tracks_one_line = []
        existing = track_numbers.copy()
        shipments = json_data['shipments']
        for shipment in shipments:
            shipment_data = shipment['shipment']['milestone']
            info_received, pickedup = shipment_data[0]['time_utc'], shipment_data[1]['time_utc']
            if info_received and pickedup:
                tracks.append([shipment['number'], info_received, pickedup])
                existing.remove(shipment['number'])
            elif info_received:
                tracks_one_line.append([shipment['number'], info_received])
                existing.remove(shipment['number'])
            elif 'Shipment information sent to FedEx' in str(shipment):
                tracks.append([shipment['number'], str(info_received), str(pickedup), 'Shipment information sent to FedEx'])
                existing.remove(shipment['number'])

        return tracks, tracks_one_line, existing

        
    async def save_result_in_file(self, tracks, tracks_one_line, nevalid):
        def sync():
            with open('1string.txt', 'a+', encoding='utf-8') as f:
                for i in tracks_one_line:
                    f.write("\n".join(i) + '\n\n')

            with open('strings.txt', 'a+', encoding='utf-8') as f:
                for i in tracks:
                    f.write("\n".join(i) + '\n\n')

            with open('nevalid.txt', 'a+', encoding='utf-8') as f:
                f.write("\n".join(nevalid) + '\n' if len(nevalid) != 0 else '')

        await asyncio.to_thread(sync)

class UnsupportedProxyType(Exception):
    def __init__(self, message):
        super().__init__(message)
        logger.error(f'{message}')