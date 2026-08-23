"""shared/scripts/soccer_name_utils.py

Shared name normalization/matching for soccer, modeled directly on
nba/scripts/name_utils.py. Used to match FPL's `first_name`/`second_name`
(fantasy.premierleague.com) against sofifa's `name` field
(shared/scripts/scrape_sofifa.py) -- the two sources don't share an ID
space (confirmed live during EPL/MLS recon), so name matching is the
only option, same situation as NHL's ratings site.

Real fields confirmed live before writing this: FPL's element has no
single full-name field -- `first_name` + ' ' + `second_name` is the
real full name (e.g. "Erling" + "Haaland"), matching sofifa's `name`
field (sofifa's own `data-tippy-content` full name, e.g. "Erling
Haaland", not its shorter on-page `short_name` like "E. Haaland").
FPL's `web_name` (e.g. "Haaland", "Salah") is the display name used on
the FPL site itself and is NOT reliably a distinct surname -- kept
available to callers as a secondary lookup key, not used as the primary
match key, since several real FPL players share the same web_name
across different teams.

SOCCER_NAME_ALIASES is populated from real unmatched-name review, same
way NBA_NAME_ALIASES was, not guessed ahead of time. Format matches
NBA's: keys are the BASE-POPULATION source's name as looked up by the
matcher (FPL's constructed full name for EPL, ESPN's `full_name` for
MLS), values are the corresponding name on whichever source is being
matched against (sofifa for both leagues; ASA for MLS's second join).
A None value forces a no-match (wrong player, don't guess). (Correcting
an earlier version of this docstring that had the key/value direction
backwards -- the actual lookup in both build_epl_match.py and
build_mls_match.py is `SOCCER_NAME_ALIASES.get(base_population_name, ...)`.)
"""
import re
import unicodedata

SOCCER_NAME_ALIASES = {
    # Ukrainian transliteration variant -- FPL and sofifa disagree on the
    # final letter of the first name, so even the team-scoped
    # token-overlap tier's first-token gate fails (its full surname
    # token does match, but that tier requires first-token equality
    # first). Confirmed same player, same club (Everton) both sides.
    'Vitalii Mykolenko': 'Vitaliy Mykolenko',
    # These three all follow the same real pattern: sofifa's full-legal-
    # name field carries a formal/additional given name FPL's
    # first_name/second_name never includes at all (a nickname on FPL's
    # side, or simply absent) -- e.g. sofifa's "José Diogo Dalot
    # Teixeira" vs FPL's "Diogo Dalot Teixeira". Since the extra token
    # leads the name, it changes the FIRST token too, so even the
    # token-overlap tier's first-token-must-match gate fails despite
    # heavy remaining overlap (Dalot/Teixeira, Jocelin/Ta/Bi,
    # González/Iglesias all shared). Confirmed same player, same club,
    # each of the 3 cases, by hand.
    'Nico González Iglesias': 'Nicolás González Iglesias',
    'Diogo Dalot Teixeira': 'José Diogo Dalot Teixeira',
    'Djiamgone Jocelin Ta Bi': 'Jocelin Ta Bi',

    # MLS (ESPN full_name -> sofifa name), found the same way: reviewed
    # build_mls_match.py's real unmatched-sofifa list, cross-checked each
    # candidate against sofifa's real per-team roster before adding it
    # here -- every entry below is a same-team confirmation (ESPN's team
    # and sofifa's team, resolved through ESPN_TO_SOFIFA_TEAM, actually
    # agree), not just a plausible-looking surname match. A same-surname,
    # different-team, different-first-name pair (e.g. ESPN's "Cavan
    # Sullivan" vs sofifa's "Quinn Sullivan", both Philadelphia Union)
    # was deliberately left OUT -- almost certainly two different real
    # players who happen to share a surname and a club, not a name
    # variant of the same person.
    'Matt Edwards': 'Matthew Edwards',
    'Benjamin Lundt': 'Ben Lundt',
    'Alexey Miranchuk': 'Aleksey Miranchuk',
    'Christopher Durkin': 'Chris Durkin',
    'Samual Rogers': 'Samuel Rogers',
    'Daniel Musovski': 'Danny Musovski',
    'Samuel Junqua': 'Sam Junqua',
    'Shapi Suleymanov': 'Magomed-Shapi Suleymanov',
    'Cheick Sabaly': 'Cheikh Sabaly',
    'Jean-Claude Ngando': 'J.C. Ngando',
    'Joshua Atencio': 'Josh Atencio',
    'Matthew Longstaff': 'Matty Longstaff',
    'Jacob Davis': 'Jake Davis',
    'Ted Ku-Dipietro': 'Theodore Ku-DiPietro',
    'William Kumado': 'Willy Kumado',
    'William Sands': 'Will Sands',
    'Nickseon Gomis': 'Nicksoen Gomis',
    'Maxi Carrizo': 'Máximo Carrizo',
    'Augustin Anello': 'Agustín Anello',
    'Andrew Baiera': 'Drew Baiera',
    'JD Gunn': 'John David Gunn',
    'Chris Applewhite': 'Christopher Applewhite',
    'Gio Villa': 'Juan Giovanni Villa',
    'Jeisson Palacios': 'Jeison Palacios',
}


def normalize_name(name):
    """Title-case a raw scraped name, fixing initials (A.J.), apostrophes,
    hyphens, and Jr./Sr./II-IV suffixes. Sport-agnostic string cleanup --
    ported from nba/scripts/name_utils.py (itself ported from
    nfl/scripts/build_master.py)."""
    if not name:
        return name
    name = name.strip()
    name = re.sub(r'\b([A-Z])([A-Z])\b',
                  lambda m: m.group(1) + '.' + m.group(2) + '.'
                  if m.group(1) != m.group(2) else m.group(0), name)
    name = name.title()
    name = re.sub(r"'([a-z])", lambda m: "'" + m.group(1).upper(), name)
    name = re.sub(r'-([a-z])', lambda m: '-' + m.group(1).upper(), name)
    name = re.sub(r'\b(Jr|Sr)\.', r'\1', name)
    name = re.sub(r'\b(Jr|Sr)\b', r'\1.', name)
    name = re.sub(r'\b(Ii|Iii|Iv|Vi)\b',
              lambda m: {'Ii': 'II', 'Iii': 'III', 'Iv': 'IV', 'Vi': 'VI'}[m.group(0)], name)
    return name


SUFFIX_WORDS = {'jr', 'sr', 'ii', 'iii', 'iv', 'vi', 'v'}


def normalize_for_matching(name):
    """Strip everything except letters, lowercase, no spaces -- for
    matching only, not display. Accented letters fold to their ASCII
    base first (Fernandez == Fernández) -- FPL and sofifa don't
    consistently agree on diacritics for the same player, so without
    this fold every accented name silently fails to match instead of
    erroring, which is worse. Ported unmodified from
    nba/scripts/name_utils.py, including its "V" vs Roman-numeral-V
    suffix-collision fix (see that file for the V.J. Edgecombe case)."""
    if not name:
        return ''
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    name = name.lower().replace('.', '')
    tokens = [t for t in name.split() if t not in SUFFIX_WORDS]
    name = ' '.join(tokens)
    name = re.sub(r'[^a-z]', '', name)
    return name
