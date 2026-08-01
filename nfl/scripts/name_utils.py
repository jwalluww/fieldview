import re

# nbadepthcharts.com/NBA's name_utils.py mirrors these two functions from
# this file's original home (build_master.py) -- this is the NFL side of
# that shared pattern, extracted the same way.

def normalize_name(name):
    """Title-case a raw OurLads name, fixing initials (A.J.), apostrophes,
    hyphens, and Jr./Sr./II-IV suffixes."""
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


def normalize_for_matching(name):
    """Strip everything except letters, lowercase, no spaces -- used for
    GSIS/Spotrac/snap-count matching, not display."""
    if not name:
        return ''
    name = name.lower()
    # Remove suffixes entirely before stripping
    name = re.sub(r'\b(jr|sr|ii|iii|iv|vi|v)\b', '', name)
    # Strip everything that isn't a letter
    name = re.sub(r'[^a-z]', '', name)
    return name


def normalize_madden(name):
    """Lowercase, strip suffixes/punctuation but KEEP spaces -- a distinct
    normalizer from normalize_for_matching() above, not a redundant one.
    find_madden_player()'s word-subset fallback (target_words.issubset(...))
    needs to split the normalized name into separate word tokens, which a
    space-stripped string can't do. Ported unchanged from the old
    merge_madden.py's normalize()."""
    if not name:
        return ''
    name = name.lower()
    name = re.sub(r'\b(jr|sr|ii|iii|iv)\b\.?', '', name)
    name = re.sub(r"[^a-z ]", "", name)
    return re.sub(r'\s+', ' ', name).strip()
