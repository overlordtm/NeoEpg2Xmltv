#!/usr/bin/env python3

import requests
import json
import time
import calendar
import logging
import argparse
from pathlib import Path
from datetime import datetime, time as dt_time
from typing import List, Dict, Any
import xmltv_alt  # Ensure this is installed: pip install xmltv-alt

# Setup logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

API_BASE_URL = "https://stargate.telekom.si/api/titan.tv"
HEADERS = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'sl-SI,sl;q=0.9,en-GB;q=0.8,en;q=0.7',
    'content-type': 'application/json',
    'dnt': '1',
    'origin': 'https://neo.io',
    'priority': 'u=1, i',
    'sec-ch-ua': '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Linux"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'cross-site',
    'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
    'x-applayout': '1',
    'x-language': 'sl',
}


def load_channel_ids(path: str) -> List[str]:
    with open(path, 'r', encoding='utf-8') as f:
        ids = [line.strip() for line in f if line.strip()]
    return list(dict.fromkeys(ids))  # Remove duplicates


def fetch_channel_info(channel_id: str) -> Dict[str, Any]:
    payload = {'channel_id': channel_id, 'timeshift': 0}
    try:
        response = requests.post(f"{API_BASE_URL}.ContentService/EpgContentDetails", headers=HEADERS, json=payload)
        response.raise_for_status()
        return response.json()['epg_details']
    except Exception as e:
        logger.warning(f"Failed to fetch channel info for {channel_id}: {e}")
        return {}


def fetch_programs(channel_id: str, from_ts: int, to_ts: int) -> List[Dict[str, Any]]:
    payload = {'ch_ext_id': channel_id, 'from': from_ts, 'to': to_ts}
    try:
        response = requests.post(f"{API_BASE_URL}.WebEpg/GetWebEpgData", headers=HEADERS, json=payload)
        response.raise_for_status()
        return response.json().get('shows', [])
    except Exception as e:
        logger.warning(f"Failed to fetch programs for {channel_id}: {e}")
        return []


def convert_channel_metadata(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'id': data.pop('channel_friendly_name'),
        'display-name': [(data.pop('channel_name'), 'sl')],
        'icon': [{'src': data.pop('channel_logo')}]
    }


def convert_program_metadata(data: Dict[str, Any], channel_id: str, tz_offset: str) -> Dict[str, Any]:
    start = datetime.fromtimestamp(data.pop('show_start')).strftime('%Y%m%d%H%M%S') + f' {tz_offset}'
    stop = datetime.fromtimestamp(data.pop('show_end')).strftime('%Y%m%d%H%M%S') + f' {tz_offset}'
    genres = data.pop('genres', [])
    return {
        'channel': channel_id,
        'title': [(data.pop('title'), 'sl')],
        'start': start,
        'stop': stop,
        'icon': [{'src': data.pop('thumbnail')}],
        'category': [(genre, 'sl') for genre in genres],
        'desc': [(data.pop('summary', ''), 'sl')]
    }


def generate_epg(channel_ids: List[str], output_file: str):
    now = datetime.now()
    midnight = datetime.combine(now, dt_time.min)
    from_ts = calendar.timegm(midnight.timetuple())
    to_ts = from_ts + 7 * 24 * 3600 - 1
    tz_offset = now.strftime('%z') or '+0200'
    timestamp_str = now.strftime('%Y%m%d%H%M%S') + f' {tz_offset}'

    writer = xmltv_alt.Writer(
        encoding="utf-8",
        date=timestamp_str,
        source_info_url='https://neo.io/',
        source_info_name='NEO',
        generator_info_url='',
        generator_info_name='neo-epg-generator'
    )

    for ch_id in channel_ids:
        logger.info(f"Processing channel: {ch_id}")

        channel_info = fetch_channel_info(ch_id)
        if not channel_info:
            continue
        channel_meta = convert_channel_metadata(channel_info)
        writer.addChannel(channel_meta)
        channel_xml_id = channel_meta['id']

        programs = fetch_programs(ch_id, from_ts, to_ts)
        logger.info(f"  Found {len(programs)} programs")

        for prog in programs:
            try:
                writer.addProgramme(convert_program_metadata(prog, channel_xml_id, tz_offset))
            except Exception as e:
                logger.warning(f"  Skipping invalid program: {e}")

        time.sleep(0.2)  # avoid hammering the API

    writer.write(output_file, pretty_print=True)
    logger.info(f"EPG written to {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Fetch and generate XMLTV EPG from NEO Telekom API")
    parser.add_argument('--ids', required=True, help="Path to text file with channel IDs")
    parser.add_argument('--output', default='epg.xmltv', help="Output XMLTV file name")
    args = parser.parse_args()

    if not Path(args.ids).exists():
        logger.error(f"File not found: {args.ids}")
        return

    channel_ids = load_channel_ids(args.ids)
    generate_epg(channel_ids, args.output)


if __name__ == "__main__":
    main()

