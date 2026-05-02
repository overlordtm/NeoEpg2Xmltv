#!/usr/bin/env python3

import time
import logging
import argparse
from pathlib import Path
from datetime import datetime

import requests
import xmltv_alt

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

API_BASE_URL = "https://stargate.telekom.si/api/titan.tv"

# Maps Slovenian API genres to Jellyfin-recognised English XMLTV categories.
# Only genres with a clear match are listed; unmapped genres are kept SL-only.
SL_TO_EN_CATEGORY: dict[str, str] = {
    # Movie
    'akcija': 'Movie',
    'animirani': 'Movie',
    'drama': 'Movie',
    'domišljijski': 'Movie',
    'fantazijski': 'Movie',
    'grozljivka': 'Movie',
    'komedija': 'Movie',
    'kriminalka': 'Movie',
    'misterij': 'Movie',
    'muzikal': 'Movie',
    'nadnaravno': 'Movie',
    'pustolovščina': 'Movie',
    'romantična komedija': 'Movie',
    'romantični': 'Movie',
    'superheroji': 'Movie',
    'triler': 'Movie',
    'vestern': 'Movie',
    'znanstvena fantastika': 'Movie',
    # Series
    'telenovela': 'Series',
    'resničnostna oddaja': 'Series',
    # Sports
    'šport': 'Sports',
    'atletika': 'Sports',
    'avto-moto šport': 'Sports',
    'bejzbol': 'Sports',
    'biljard': 'Sports',
    'boks': 'Sports',
    'borilni šport': 'Sports',
    'e-šport': 'Sports',
    'ekstremni šport': 'Sports',
    'golf': 'Sports',
    'hokej': 'Sports',
    'jadranje': 'Sports',
    'kolesarstvo': 'Sports',
    'konjeništvo': 'Sports',
    'košarka': 'Sports',
    'nogomet': 'Sports',
    'odbojka': 'Sports',
    'plavanje': 'Sports',
    'plezanje': 'Sports',
    'ragbi': 'Sports',
    'rokomet': 'Sports',
    'sabljanje': 'Sports',
    'tenis': 'Sports',
    'vodni šport': 'Sports',
    # Kids
    'otroška oddaja': 'Kids',
    'otroški ali mladinski': 'Kids',
    'risanka': 'Kids',
    # News
    'dnevno-informativna oddaja': 'News',
    'informativna oddaja': 'News',
    'pogovorna oddaja': 'News',
    'vreme': 'News',
    # Documentary
    'dokumentarec': 'Documentary',
    'družba': 'Documentary',
    'družboslovje': 'Documentary',
    'narava': 'Documentary',
    'naravoslovje': 'Documentary',
    'potovanje': 'Documentary',
    'poljudnoznanstveno': 'Documentary',
    'reportaža': 'Documentary',
    'zgodovina': 'Documentary',
    'zdravje': 'Documentary',
    'življenjski slog': 'Documentary',
    'znanost': 'Documentary',
}

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


def load_channel_ids(path: str) -> list[str]:
    with open(path, encoding='utf-8') as f:
        ids = [line.strip() for line in f if line.strip()]
    return list(dict.fromkeys(ids))


def fetch_channel_info(channel_id: str) -> dict:
    payload = {'channel_id': channel_id, 'timeshift': 0}
    try:
        response = requests.post(f"{API_BASE_URL}.ContentService/EpgContentDetails", headers=HEADERS, json=payload)
        response.raise_for_status()
        return response.json()['epg_details']
    except Exception as e:
        logger.warning(f"Failed to fetch channel info for {channel_id}: {e}")
        return {}


def fetch_programs(channel_id: str, from_ts: int, to_ts: int) -> list[dict]:
    payload = {'ch_ext_id': channel_id, 'from': from_ts, 'to': to_ts}
    try:
        response = requests.post(f"{API_BASE_URL}.WebEpg/GetWebEpgData", headers=HEADERS, json=payload)
        response.raise_for_status()
        return response.json().get('shows', [])
    except Exception as e:
        logger.warning(f"Failed to fetch programs for {channel_id}: {e}")
        return []


def convert_channel_metadata(data: dict) -> dict:
    return {
        'id': data.pop('channel_friendly_name'),
        'display-name': [(data.pop('channel_name'), 'sl')],
        'icon': [{'src': data.pop('channel_logo')}],
    }


def convert_program_metadata(data: dict, channel_id: str, tz_offset: str) -> dict:
    start = datetime.fromtimestamp(data.pop('show_start')).strftime('%Y%m%d%H%M%S') + f' {tz_offset}'
    stop = datetime.fromtimestamp(data.pop('show_end')).strftime('%Y%m%d%H%M%S') + f' {tz_offset}'
    genres = data.pop('genres', [])
    categories = []
    en_seen = set()
    for genre in genres:
        categories.append((genre, 'sl'))
        en = SL_TO_EN_CATEGORY.get(genre)
        if en and en not in en_seen:
            categories.append((en, 'en'))
            en_seen.add(en)
    return {
        'channel': channel_id,
        'title': [(data.pop('title'), 'sl')],
        'start': start,
        'stop': stop,
        'icon': [{'src': data.pop('thumbnail')}],
        'category': categories,
        'desc': [(data.pop('summary', ''), 'sl')],
    }


def generate_epg(channel_ids: list[str], output_file: str):
    now = datetime.now().astimezone()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    from_ts = int(midnight.timestamp())
    to_ts = from_ts + 7 * 24 * 3600 - 1
    tz_offset = now.strftime('%z')
    timestamp_str = now.strftime('%Y%m%d%H%M%S') + f' {tz_offset}'

    writer = xmltv_alt.Writer(
        encoding="utf-8",
        date=timestamp_str,
        source_info_url='https://neo.io/',
        source_info_name='NEO',
        generator_info_url='',
        generator_info_name='neo-epg-generator',
    )

    failed_info: list[str] = []
    no_programs: list[str] = []

    for ch_id in channel_ids:
        logger.info(f"Processing channel: {ch_id}")

        channel_info = fetch_channel_info(ch_id)
        if not channel_info:
            failed_info.append(ch_id)
            continue
        channel_meta = convert_channel_metadata(channel_info)
        writer.addChannel(channel_meta)
        channel_xml_id = channel_meta['id']

        programs = fetch_programs(ch_id, from_ts, to_ts)
        logger.info(f"  Found {len(programs)} programs")
        if not programs:
            no_programs.append(ch_id)

        for prog in programs:
            try:
                writer.addProgramme(convert_program_metadata(prog, channel_xml_id, tz_offset))
            except Exception as e:
                logger.warning(f"  Skipping invalid program: {e}")

        time.sleep(0.2)

    writer.write(output_file, pretty_print=True)
    logger.info(f"EPG written to {output_file}")

    if failed_info:
        logger.warning(f"Failed to fetch channel info ({len(failed_info)}): {', '.join(failed_info)}")
    if no_programs:
        logger.info(f"No programs returned ({len(no_programs)}): {', '.join(no_programs)}")


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
