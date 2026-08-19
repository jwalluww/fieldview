"""nhl/scripts/name_utils.py

Ported directly from nba/scripts/name_utils.py -- same sport-agnostic
name cleanup/matching logic, just renamed for NHL. NHL_NAME_ALIASES
starts empty; populate it the same way NBA's was built, by reading
scrape_ratings.py's unmatched output and adding real mismatches found
there (a None value forces a no-match, for a wrong-player alias).
"""
import re
import unicodedata

NHL_NAME_ALIASES = {}


def normalize_name(name):
    """Title-case a raw scraped name, fixing initials (A.J.), apostrophes,
    hyphens, and Jr./Sr./II-IV suffixes. Sport-agnostic string cleanup --
    ported from nba/scripts/name_utils.py / nfl/scripts/build_master.py."""
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
    ASCII base first (e.g. Marner == Marner, but also handles cases
    like Djoos/Ďjoos-style diacritic divergence between sources).

    Suffix words are dropped only as whole whitespace-delimited tokens,
    checked *before* punctuation is stripped -- see nba/scripts/name_utils.py
    for why (a naive post-punctuation-strip regex mistakes a lone "V."
    initial for a Roman-numeral suffix)."""
    if not name:
        return ''
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    name = name.lower().replace('.', '')
    tokens = [t for t in name.split() if t not in SUFFIX_WORDS]
    name = ' '.join(tokens)
    name = re.sub(r'[^a-z]', '', name)
    return name
