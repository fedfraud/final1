import logging
import asyncio
import time
import random
import ssl
from typing import Optional, Dict, List, Set
from aiohttp import ClientSession, ClientError, TCPConnector, ClientTimeout
from aiohttp.client_exceptions import (
    ClientProxyConnectionError, 
    ClientHttpProxyError,
    ClientSSLError,
    ClientConnectorError,
    ServerDisconnectedError
)
from utils import Utils
from logger import *
from generate import generate_last_id, get_time_offset
import json

class Fedex():    
    def __init__(self) -> None:
        self.utils = Utils()
        self.request_timeout = 30
        self.max_retries = 100
        self.base_retry_delay = 1
        self.max_retry_delay = 30
        
    def _create_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context with fallback settings for problematic connections."""
        ssl_context = ssl.create_default_context()
        
        # Allow fallback for problematic SSL connections
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        # Set SSL version and cipher suites for better compatibility
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        ssl_context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
        
        return ssl_context
        
    def _create_connector(self) -> TCPConnector:
        """Create TCP connector with proper SSL context and connection settings."""
        ssl_context = self._create_ssl_context()
        
        return TCPConnector(
            ssl_context=ssl_context,
            limit=100,
            limit_per_host=30,
            ttl_dns_cache=300,
            use_dns_cache=True,
            keepalive_timeout=30,
            enable_cleanup_closed=True,
            force_close=False
        )
        
    def _create_timeout(self) -> ClientTimeout:
        """Create timeout configuration for requests."""
        return ClientTimeout(
            total=self.request_timeout,
            connect=10,
            sock_read=15,
            sock_connect=10
        )
        
    def _calculate_retry_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay for retries."""
        delay = self.base_retry_delay * (2 ** attempt)
        # Add jitter to avoid thundering herd
        jitter = random.uniform(0.1, 0.5)
        return min(delay + jitter, self.max_retry_delay)

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
            except (ClientProxyConnectionError, ClientHttpProxyError) as e:
                logger.warning(f"Proxy error (attempt {retry_count + 1}/{self.max_retries}): {str(e)}")
                last_exception = e
                retry_count += 1
                await asyncio.sleep(self._calculate_retry_delay(retry_count))
                
            except (ClientSSLError, ClientConnectorError) as e:
                logger.warning(f"SSL/Connection error (attempt {retry_count + 1}/{self.max_retries}): {str(e)}")
                last_exception = e
                retry_count += 1
                await asyncio.sleep(self._calculate_retry_delay(retry_count))
                
            except ServerDisconnectedError as e:
                logger.warning(f"Server disconnected (attempt {retry_count + 1}/{self.max_retries}): {str(e)}")
                last_exception = e
                retry_count += 1
                await asyncio.sleep(self._calculate_retry_delay(retry_count))
                
            except APIRateLimit as e:
                logger.warning(f"Rate limit hit (attempt {retry_count + 1}/{self.max_retries}): {str(e)}")
                last_exception = e
                retry_count += 1
                # Longer delay for rate limits
                await asyncio.sleep(self._calculate_retry_delay(retry_count) * 2)
                
            except asyncio.TimeoutError as e:
                logger.warning(f"Request timeout (attempt {retry_count + 1}/{self.max_retries}): {str(e)}")
                last_exception = e
                retry_count += 1
                await asyncio.sleep(self._calculate_retry_delay(retry_count))
                
            except Exception as e:
                logger.error(f"Unexpected error processing tracks (attempt {retry_count + 1}/{self.max_retries}): {str(e)}")
                # For unexpected errors, still try a few more times
                if retry_count < 5:  # Only retry unexpected errors a few times
                    last_exception = e
                    retry_count += 1
                    await asyncio.sleep(self._calculate_retry_delay(retry_count))
                else:
                    await self._save_unchecked_tracks(track_numbers, unchecked_string_filename)
                    return {}

        logger.error(f"Failed after {self.max_retries} attempts. Last error: {str(last_exception)}")
        await self._save_unchecked_tracks(track_numbers, unchecked_string_filename)
        return {}

    async def _validate_connection(self, session: ClientSession, url: str) -> bool:
        """Validate connection to the target server before processing tracks."""
        try:
            async with session.get(url.replace('/track/restapi', ''), timeout=5) as response:
                return response.status in [200, 301, 302, 403, 404]  # Any response means connection works
        except Exception:
            return False
            
    async def _process_tracks(self, track_numbers: Set[str], proxy_path: str, filename: str, 
                            one_string_filename: str, unchecked_string_filename: str, 
                            not_found_filename: str) -> Dict:
        proxy = self.utils.get_random_proxy(proxy_path)
        if proxy_path and not proxy:
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
        
        # Create connector and timeout
        connector = self._create_connector()
        timeout = self._create_timeout()
        
        try:
            async with ClientSession(
                headers=headers, 
                connector=connector, 
                timeout=timeout
            ) as session:
                # Validate connection first
                if not await self._validate_connection(session, url):
                    raise ClientConnectorError("Unable to establish connection to t.17track.net")
                
                if len(track_numbers) > 40:
                    raise APITooManyElements("API too many elements exception")
                
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
        finally:
            # Ensure connector is properly closed
            await connector.close()
                
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

class APITooManyElements(Exception):
    def __init__(self, message):
        super().__init__(message)
        logger.error(f'{message}')

class APIRateLimit(Exception):
    def __init__(self, message):
        super().__init__(message)