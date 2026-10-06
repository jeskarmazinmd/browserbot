"""G3 actual-quantity accounting, separate from risk-resized legacy rows."""
from generation_three_paper_tracker import FILE_STEM, IDS
from strategies import generation_three
from reporting.generation_one_performance import calculate_generation_one

def calculate_generation_three(root,day,cutoff,marks,quote_for):
    return calculate_generation_one(root,day,cutoff,marks,quote_for,
        file_stem=FILE_STEM,ids=IDS,flash_catalog=generation_three,
        minute_catalog=generation_three.MINUTE_CATALOG,
        engine_name='generation_three_bidask_independent')
