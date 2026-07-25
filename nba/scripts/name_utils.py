import re
import unicodedata

# Known name mismatches between Spotrac and nba_api, discovered from the
# unmatched list -- same pattern as NFL's NAME_ALIASES in
# nfl/scripts/build_master.py (Riq Woolen / Dru Phillips style fixes).
# Format: 'spotrac_name': 'nba_api_name'. A None value forces a no-match
# (wrong player, don't guess).
NBA_NAME_ALIASES = {
    'Herb Jones': 'Herbert Jones',
    'Nicolas Claxton': 'Nic Claxton',
    'Ron Holland II': 'Ronald Holland II',
    'Sviatoslav Mykhailiuk': 'Svi Mykhailiuk',
    'Mohamed Bamba': 'Mo Bamba',
    'Cameron Christie': 'Cam Christie',
    "Nah'Shon Hyland": 'Bones Hyland',
    'Cameron Thomas': 'Cam Thomas',
}


def normalize_name(name):
    """Title-case a raw scraped name, fixing initials (A.J.), apostrophes,
    hyphens, and Jr./Sr./II-IV suffixes. Sport-agnostic string cleanup --
    ported from nfl/scripts/build_master.py."""
    if not name:
        return name
    name = name.strip()
    # Fix true initials (AJ, BJ, CJ) BEFORE title case
    # But NOT roman numerals (II, III) -- exclude repeated same letter
    name = re.sub(r'\b([A-Z])([A-Z])\b',
                  lambda m: m.group(1) + '.' + m.group(2) + '.'
                  if m.group(1) != m.group(2) else m.group(0), name)
    name = name.title()
    # Fix apostrophe casing
    name = re.sub(r"'([a-z])", lambda m: "'" + m.group(1).upper(), name)
    # Fix hyphenated
    name = re.sub(r'-([a-z])', lambda m: '-' + m.group(1).upper(), name)
    # Fix suffixes -- must run AFTER title case
    name = re.sub(r'\b(Jr|Sr)\.', r'\1', name)
    name = re.sub(r'\b(Jr|Sr)\b', r'\1.', name)
    name = re.sub(r'\b(Ii|Iii|Iv|Vi)\b',
              lambda m: {'Ii': 'II', 'Iii': 'III', 'Iv': 'IV', 'Vi': 'VI'}[m.group(0)], name)
    return name


SUFFIX_WORDS = {'jr', 'sr', 'ii', 'iii', 'iv', 'vi', 'v'}


def normalize_for_matching(name):
    """Strip everything except letters, lowercase, no spaces -- for
    matching only, not display. Accented letters are folded to their
    ASCII base first (Doncic == Dončić) -- Spotrac and nba_api don't
    agree on diacritics for the same player, so without this fold every
    accented name (Jokic/Jokić, Doncic/Dončić, ...) silently fails to
    match instead of erroring, which is worse.

    Suffix words are dropped only as whole whitespace-delimited tokens,
    checked *before* punctuation is stripped. A naive \\b(...|v)\\b regex
    run after periods are removed will mistake a lone initial for the
    "V" suffix -- "V.J. Edgecombe" has "v" flanked by word boundaries on
    both sides of its period, so it gets stripped as if it were a Roman
    numeral suffix, producing "jedgecombe" instead of "vjedgecombe"."""
    if not name:
        return ''
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    name = name.lower().replace('.', '')
    tokens = [t for t in name.split() if t not in SUFFIX_WORDS]
    name = ' '.join(tokens)
    name = re.sub(r'[^a-z]', '', name)
    return name
