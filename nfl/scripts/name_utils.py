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
    # But NOT roman numerals (II, III, IV, VI) -- exclude both repeated
    # same letter (II) AND the two DIFFERENT-letter Roman numerals (IV,
    # VI). Without the second exclusion, "IV" is two different uppercase
    # letters and gets treated as initials here, producing "I.V." before
    # the suffix-fixing regex below ever gets a clean "Iv" token to
    # recognize -- confirmed live: "Will Mcdonald IV" -> "Will Mcdonald I.V."
    name = re.sub(r'\b([A-Z])([A-Z])\b',
                  lambda m: m.group(0)
                  if m.group(1) == m.group(2) or m.group(0).upper() in ('IV', 'VI')
                  else m.group(1) + '.' + m.group(2) + '.', name)
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
    """Strip everything except letters, lowercase, no spaces -- used for
    GSIS/Spotrac/snap-count matching, not display.

    Suffix words are dropped only as whole whitespace-delimited tokens,
    checked *before* punctuation is stripped -- a naive \\b(...|v)\\b regex
    run after periods are removed mistakes a lone initial for the "V"
    suffix: "V.J. Payne" has "v" flanked by word boundaries on both sides
    of its period, so it gets stripped as if it were a Roman-numeral
    suffix, producing "jpayne" instead of "vjpayne". Same bug and fix as
    NBA's name_utils.py."""
    if not name:
        return ''
    name = name.lower().replace('.', '')
    tokens = [t for t in name.split() if t not in SUFFIX_WORDS]
    name = ' '.join(tokens)
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
