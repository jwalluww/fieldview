from datetime import date

def get_current_season():
    """NFL season is named by the year it starts (Sept–Feb).
    Before September, the most recently completed season is the prior year's."""
    today = date.today()
    return today.year if today.month >= 9 else today.year - 1