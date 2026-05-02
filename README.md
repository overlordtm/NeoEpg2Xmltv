# NEO EPG Generator

Converts Telekom Slovenije's NEO TV EPG data to [XMLTV](https://wiki.xmltv.org/) format, ready for use with Jellyfin and other media servers.

## Features

- Fetches 7 days of program guide data
- Supports multiple channels (IDs loaded from 'channel_ids.txt')
- Outputs standards-compliant `epg.xmltv` file

## Usage

```bash
uv run NeoEpgGrabber.py --ids channel_ids.txt --output epg.xmltv
```

https://overlordtm.github.io/NeoEpg2Xmltv/epg.xmltv