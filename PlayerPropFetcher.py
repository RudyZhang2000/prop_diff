
import requests
from typing import List, Dict
import json
import os

class PlayerProp:
    def __init__(self, player: str, sport: str, prop_type: str, line: float, source: str,
                 higher_mult: float = 1.0, lower_mult: float = 1.0):
        self.player = player
        self.sport = sport
        self.prop_type = prop_type
        self.line = line
        self.source = source
        self.higher_mult = higher_mult
        self.lower_mult = lower_mult

    def to_dict(self) -> Dict:
        return {
            'player': self.player,
            'sport': self.sport,
            'prop_type': self.prop_type,
            'line': self.line,
            'source': self.source
        }

def fetch_prizepicks_props() -> List[PlayerProp]:
    pp_url = "https://api.prizepicks.com/projections"
    scrapingant_key = os.environ.get('SCRAPINGANT_API_KEY')
    if scrapingant_key:
        # Route through ScrapingAnt residential proxy to bypass datacenter IP block
        # browser=true renders JS which bypasses PerimeterX bot detection
        resp = requests.get(
            'https://api.scrapingant.com/v2/general',
            params={'url': pp_url, 'x-api-key': scrapingant_key, 'browser': 'false', 'return_page_source': 'true'},
            timeout=60
        )
    else:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36',
            'Accept': 'application/json',
        }
        resp = requests.get(pp_url, headers=headers, timeout=15)
    if resp.status_code != 200:
        print(f"PrizePicks returned {resp.status_code}: {resp.text[:200]}", flush=True)
        return []
    try:
        data = resp.json()
    except Exception as e:
        print(f"Error parsing PrizePicks JSON: {e}")
        return []
    data_list = data.get('data', [])
    included = data.get('included', [])
    # Build league id -> league name lookup from included
    league_lookup = {}
    player_lookup = {}
    for inc in included:
        if inc.get('type') == 'league':
            league_lookup[inc['id']] = inc.get('attributes', {}).get('name', '')
        elif inc.get('type') == 'new_player':
            player_lookup[inc['id']] = inc.get('attributes', {}).get('display_name', '') or inc.get('attributes', {}).get('name', '')
    props = []
    for item in data_list:
        # Skip alternate/promo lines — only use the standard main line
        if item.get('attributes', {}).get('odds_type') != 'standard':
            continue
        new_player_id = item.get('relationships', {}).get('new_player', {}).get('data', {}).get('id', '')
        player = player_lookup.get(new_player_id) or item.get('attributes', {}).get('description', '')
        league_id = item.get('relationships', {}).get('league', {}).get('data', {}).get('id', '')
        sport = league_lookup.get(league_id, league_id)
        stat_type = item.get('attributes', {}).get('stat_type', '')
        line = item.get('attributes', {}).get('line_score', None)
        if stat_type and line is not None:
            props.append(PlayerProp(player, sport, stat_type, line, 'PrizePicks'))
    return props

def fetch_underdog_props() -> List[PlayerProp]:
    url = "https://api.underdogfantasy.com/beta/v5/over_under_lines"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
        "Accept": "application/json"
    }
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return []
    try:
        data = resp.json()
    except Exception as e:
        print(f"Error parsing Underdog JSON: {e}")
        return []

    # Build player lookup: player_id -> {full_name, sport_id}
    player_lookup = {}
    for player in data.get('players', []):
        pid = player.get('id', '')
        first = player.get('first_name') or ''
        last = player.get('last_name') or ''
        full_name = f"{first} {last}".strip() if first else last.strip()
        player_lookup[pid] = {'name': full_name, 'sport_id': player.get('sport_id', '')}

    # Build appearance lookup: appearance_id -> player_id
    appearance_lookup = {}
    for appearance in data.get('appearances', []):
        appearance_lookup[appearance.get('id', '')] = appearance.get('player_id', '')

    props = []
    seen = set()
    for line in data.get('over_under_lines', []):
        if line.get('status') != 'active':
            continue
        if line.get('line_type') != 'balanced':
            continue
        stat_value = line.get('stat_value')
        if stat_value is None:
            continue
        over_under = line.get('over_under', {})
        appearance_stat = over_under.get('appearance_stat', {})
        appearance_id = appearance_stat.get('appearance_id', '')
        stat_name = appearance_stat.get('display_stat', '')
        player_id = appearance_lookup.get(appearance_id, '')
        player_info = player_lookup.get(player_id, {})
        player_name = player_info.get('name', '')
        sport_id = player_info.get('sport_id', '')
        if player_name and stat_name:
            key = (player_name, sport_id, stat_name)
            if key not in seen:
                seen.add(key)
                higher_mult = 1.0
                lower_mult = 1.0
                for opt in line.get('options', []):
                    choice = opt.get('choice', '')
                    mult = float(opt.get('payout_multiplier', 1.0))
                    if choice == 'higher':
                        higher_mult = mult
                    elif choice == 'lower':
                        lower_mult = mult
                props.append(PlayerProp(player_name, sport_id, stat_name, float(stat_value), 'Underdog',
                                        higher_mult=higher_mult, lower_mult=lower_mult))

    return props
