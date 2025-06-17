import time
import asyncio

from logger import *
from datetime import datetime
from utils import Utils
from fedex import Fedex

def get_current_time() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

async def run(threads: int) -> None:
    utils = Utils()
    fedex = Fedex()

    data_path = utils.choose_txt_file('Выберите .txt файл с трек-номерами')
    proxy_path = utils.choose_txt_file('Выберите .txt файл с прокси')
    result_filename = f'{int(time.time())}_tracks.txt'
    one_string_result_filename = f'{int(time.time())}_1strings.txt'
    unchecked_string_filename = f'{int(time.time())}_unchecked.txt'
    not_found_filename = f'{int(time.time())}_not_found.txt'

    tasks = []
    set_list = []
    with open(data_path, "r", encoding="utf-8") as stream:
        i = 0
        s = set()
        for line in stream:
            if i != 0 and i % 39 == 0:
                i = 0
                set_list.append(set(s))
                s.clear()
            i = i + 1
            s.add(line.strip())
        if s:  # Add remaining tracks if any
            set_list.append(set(s))
            
    for st in set_list:
        tasks.append(asyncio.ensure_future(
            fedex.save_track_data(
                st, 
                proxy_path, 
                result_filename, 
                one_string_result_filename, 
                unchecked_string_filename,
                not_found_filename
            )
        ))
    
    sem = asyncio.Semaphore(threads)
    async with sem:
        responses = asyncio.gather(*tasks)
        await responses

def main() -> None:
    logger.info(f'Начало работы программы: {get_current_time()}')
    threads = 25
    asyncio.run(run(threads))
    logger.info(f'Завершение работы программы: {get_current_time()}')

if __name__ == '__main__':
    main()