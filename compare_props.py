from PlayerPropFetcher import fetch_prizepicks_props, fetch_underdog_props, PlayerProp
from collections import defaultdict
import re
import unicodedata

_WORD_MAP = {
    'rebounds': 'rebs',
    'assists': 'asts',
    'points': 'pts',
    'blocks': 'blks',
    'steals': 'stls',
    'block': 'blks',
    'steal': 'stls',
}

# Full-phrase mappings (applied after lowercasing, longest first to avoid partial matches)
# Bridges naming differences between PrizePicks and Underdog for specific sports
_PHRASE_MAP = {
    'shots on target': 'sot',        # Soccer: UD → PP
    'shots on goal': 'sog',          # NHL: UD → PP
    'shots attempted': 'shots',      # Soccer: UD → PP
    'goals allowed': 'goals against', # Soccer/NHL: UD → PP
    'power play points': 'power play points',  # NHL: already same, explicit for clarity
}

def normalize_prop_type(prop_type: str) -> str:
    # Remove spaces around + and normalize to lowercase
    normalized = prop_type.replace(' + ', '+').replace('+ ', '+').replace(' +', '+').lower()
    # Apply full-phrase replacements first (longest phrases first)
    for phrase, replacement in sorted(_PHRASE_MAP.items(), key=lambda x: -len(x[0])):
        normalized = normalized.replace(phrase, replacement)
    # Replace full words with abbreviations
    for full, abbr in _WORD_MAP.items():
        normalized = normalized.replace(full, abbr)
    # Normalize esports: "kills on maps 1+2" → "maps 1-2 kills"
    # Handles both "X on maps N+M" and "X on map N" patterns
    match = re.match(r'^(.+?)\s+on\s+(maps?\s+[\d]+(?:[+\-]\d+)*)$', normalized)
    if match:
        stat = match.group(1).strip()
        map_spec = match.group(2).replace('+', '-').strip()
        normalized = f"{map_spec} {stat}"
    # Normalize "+" to "-" in already-correct "maps 1+2" format, and collapse sequences "1+2+3" → "1-3"
    def collapse_map_range(m):
        prefix = m.group(1)
        raw = m.group(2)
        nums = list(map(int, re.split(r'[+\-]', raw)))
        # PP uses compact range notation "1-3" (meaning maps 1 through 3).
        # Splitting gives only endpoints [1, 3], so treat any "-" separated pair as a range.
        if len(nums) == 2 and '-' in raw:
            return f"{prefix}{nums[0]}-{nums[-1]}"
        if len(nums) > 1 and nums == list(range(nums[0], nums[-1] + 1)):
            return f"{prefix}{nums[0]}-{nums[-1]}"
        return f"{prefix}{'+'.join(map(str, nums))}"
    normalized = re.sub(r'(maps?\s+)([\d][+\-\d]*)', collapse_map_range, normalized)
    return normalized

_SPORT_MAP = {
    'VAL': 'Esports',
    'VaLORANT': 'Esports',
    'CS2': 'Esports',
    'CS': 'Esports',
    'LoL': 'Esports',
    'LOL': 'Esports',
    'Dota2': 'Esports',
    'ESPORTS': 'Esports',
}

def normalize_sport(sport: str) -> str:
    return _SPORT_MAP.get(sport, sport)

def normalize_player(player: str) -> str:
    # Strip accents (e.g. Jokić → Jokic)
    nfkd = unicodedata.normalize('NFKD', player)
    ascii_str = nfkd.encode('ascii', 'ignore').decode('ascii')
    # Normalize hyphens to spaces (e.g. Gilgeous-Alexander → Gilgeous Alexander)
    return ascii_str.lower().strip().replace('-', ' ')

def compare_props(prizepicks_props, underdog_props):
    # Index by (normalized_player, normalized_sport, normalized_prop_type)
    pp_dict = {(normalize_player(p.player), normalize_sport(p.sport), normalize_prop_type(p.prop_type)): p for p in prizepicks_props}
    ud_dict = {(normalize_player(p.player), normalize_sport(p.sport), normalize_prop_type(p.prop_type)): p for p in underdog_props}
    all_keys = set(pp_dict.keys()) | set(ud_dict.keys())
    diffs = []
    for key in all_keys:
        pp = pp_dict.get(key)
        ud = ud_dict.get(key)
        display_prop_type = pp.prop_type if pp else ud.prop_type
        if pp and ud:
            if pp.line != ud.line:
                # Which direction would you bet on UD?
                # PP < UD → take lower on UD; PP > UD → take higher on UD
                relevant_mult = ud.lower_mult if pp.line < ud.line else ud.higher_mult
                # Skip if the relevant UD direction doesn't exist (no option offered)
                if relevant_mult is None:
                    continue
                diffs.append({
                    'player': key[0].title(),
                    'sport': key[1],
                    'prop_type': display_prop_type,
                    'prizepicks_line': pp.line,
                    'underdog_line': ud.line,
                    'ud_relevant_mult': round(relevant_mult, 3)
                })
    return diffs

if __name__ == "__main__":
    pp_props = fetch_prizepicks_props()
    ud_props = fetch_underdog_props()
    diffs = compare_props(pp_props, ud_props)

    def sort_key(d):
        pp, ud = d['prizepicks_line'], d['underdog_line']
        if pp is not None and ud is not None:
            avg = (pp + ud) / 2
            pct_diff = abs(pp - ud) / avg if avg != 0 else 0
            mult = d.get('ud_relevant_mult', 1.0)
            return (0, -(pct_diff * mult ** 6))
        return (1, 0)

    diffs.sort(key=sort_key)

    output_file = "prop_diffs.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        for diff in diffs:
            f.write(str(diff) + "\n")
    print(f"Done. {len(diffs)} props written to {output_file}")
