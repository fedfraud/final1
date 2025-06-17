import logging
import asyncio
import time
import random
import ssl
from typing import Optional, Dict, List, Set
from aiohttp import ClientSession, ClientError, ClientTimeout, TCPConnector, ClientConnectorError, ClientSSLError, ServerDisconnectedError
from aiohttp.client_exceptions import ClientProxyConnectionError, ClientHttpProxyError
from utils import Utils
from logger import *
from generate import generate_last_id, get_time_offset
import json

class Fedex():    
    def __init__(self) -> None:
        self.utils = Utils()
        self.request_timeout = 30
        self.max_retries = 100
        self.retry_base_delay = 1
        self.retry_max_delay = 60
        
        # Create SSL context with fallback settings
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
        # Connector will be created when needed
        self.connector = None
    
    def _get_connector(self) -> TCPConnector:
        """Get or create the TCP connector"""
        if self.connector is None:
            self.connector = TCPConnector(
                ssl=self.ssl_context,
                limit=100,
                limit_per_host=30,
                ttl_dns_cache=300,
                use_dns_cache=True,
                keepalive_timeout=30,
                enable_cleanup_closed=True
            )
        return self.connector

    async def save_track_data(self, track_numbers: Set[str], proxy_path: Optional[str] = None, 
                            filename: str = None, one_string_filename: str = None, 
                            unchecked_string_filename: str = None, not_found_filename: str = None) -> Dict:
        retry_count = 0
        last_exception = None
        while retry_count < self.max_retries:
            try:
                return await self._process_tracks(
                    track_numbers, 
                    proxy_path, 
                    filename, 
                    one_string_filename, 
                    unchecked_string_filename, 
                    not_found_filename
                )
            except (ClientProxyConnectionError, ClientHttpProxyError, APIRateLimit) as e:
                logger.warning(f"Proxy/Rate limit error (attempt {retry_count + 1}/{self.max_retries}): {str(e)}")
                last_exception = e
                retry_count += 1
                await self._exponential_backoff(retry_count)
            except (ClientSSLError, ssl.SSLError) as e:
                logger.warning(f"SSL error (attempt {retry_count + 1}/{self.max_retries}): {str(e)}")
                last_exception = e
                retry_count += 1
                await self._exponential_backoff(retry_count)
            except (ClientConnectorError, ServerDisconnectedError) as e:
                logger.warning(f"Connection error (attempt {retry_count + 1}/{self.max_retries}): {str(e)}")
                last_exception = e
                retry_count += 1
                await self._exponential_backoff(retry_count)
            except asyncio.TimeoutError as e:
                logger.warning(f"Timeout error (attempt {retry_count + 1}/{self.max_retries}): {str(e)}")
                last_exception = e
                retry_count += 1
                await self._exponential_backoff(retry_count)
            except Exception as e:
                logger.error(f"Unexpected error processing tracks: {str(e)}")
                await self._save_unchecked_tracks(track_numbers, unchecked_string_filename)
                return {}

        logger.error(f"Failed after {self.max_retries} attempts. Last error: {str(last_exception)}")
        await self._save_unchecked_tracks(track_numbers, unchecked_string_filename)
        return {}
    
    async def _exponential_backoff(self, retry_count: int) -> None:
        """Implement exponential backoff with jitter"""
        delay = min(self.retry_base_delay * (2 ** retry_count), self.retry_max_delay)
        jitter = random.uniform(0.1, 0.3) * delay
        total_delay = delay + jitter
        logger.debug(f"Waiting {total_delay:.2f} seconds before retry")
        await asyncio.sleep(total_delay)

    async def _process_tracks(self, track_numbers: Set[str], proxy_path: str, filename: str, 
                            one_string_filename: str, unchecked_string_filename: str, 
                            not_found_filename: str) -> Dict:
        proxy = self.utils.get_random_proxy(proxy_path)
        if not proxy:
            raise ClientProxyConnectionError("No valid proxy available")

        track_data = {}
        body = {'data': [{'num': number, 'fc': '100003', 'sc': 0} for number in track_numbers], 'guid': '', 'timeZoneOffset': int(get_time_offset())}
        last_id, cookie = generate_last_id(body)
        body = json.dumps(body, separators=(",", ":"))
        url = 'https://t.17track.net/track/restapi'
        headers = {
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://t.17track.net",
            "Referer": "https://t.17track.net/en",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/137.0.0.0 Safari/537.36"
            ),
            "X-Requested-With": "XMLHttpRequest",
            "last-event-id": last_id,
            "Cookie": f"_yq_bid={cookie};",
        }
        # Create timeout configuration
        timeout = ClientTimeout(total=self.request_timeout, connect=10, sock_read=15)
        
        async with ClientSession(
            headers=headers, 
            connector=self._get_connector(), 
            timeout=timeout
        ) as session:
            if len(track_numbers) > 40:
                raise APITooManyElements("API too many elements exception")
            
            try:
                async with session.post(
                    url, 
                    data=body, 
                    proxy=proxy
                ) as r:
                    if r.status != 200:
                        raise ClientError(f"HTTP error {r.status}")

                    track_data = await r.json()

                    if 'abN' in str(track_data) or 'uIP' in str(track_data):
                        raise APIRateLimit(track_data)

                    tracks, onestring, nevalid = self.utils.parse_17track_response(track_data, track_numbers)

                    await self.utils.save_result_in_file(
                        tracks,
                        onestring,
                        nevalid
                    )

                    logger.info(f'2strings: {len(tracks)} | 1string: {len(onestring)} | nevalid: {len(nevalid)}')

                    return None
                    
            except asyncio.TimeoutError:
                raise ClientError("Request timed out")
                
    async def _save_unchecked_tracks(self, track_numbers: Set[str], filename: str = 'unchecked.txt'):
        if not track_numbers:
            return
            
        def sync():
            with open('unchecked.txt', 'a+', encoding='utf-8') as out:
                for track in track_numbers:
                    out.write(f"{track}\n")
        await asyncio.to_thread(sync)
        
    async def _save_not_found_tracks(self, track_numbers: Set[str], filename: str):
        if not track_numbers:
            return
            
        def sync():
            with open(filename, 'a+', encoding='utf-8') as out:
                for track in track_numbers:
                    out.write(f"{track}\n")
        await asyncio.to_thread(sync)
    
    async def close(self):
        """Close the connector and cleanup resources"""
        if hasattr(self, 'connector') and self.connector:
            await self.connector.close()

class APITooManyElements(Exception):
    def __init__(self, message):
        super().__init__(message)
        logger.error(f'{message}')

class APIRateLimit(Exception):
    def __init__(self, message):
        super().__init__(message)