from datetime import date

def get_current_season():
    """NFL season is named by the year it starts (Sept–Feb).
    Before September, the most recently completed season is the prior year's."""
    today = date.today()
    return today.year if today.month >= 9 else today.year - 1

def calculate_age(birth_date):
    """Full years old as of today, from a date/datetime/pandas Timestamp.
    Real calendar age (not season-anchored like years_pro), matching what
    Madden's own age field used to report."""
    if birth_date is None:
        return None
    born = birth_date.date() if hasattr(birth_date, 'date') else birth_date
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))