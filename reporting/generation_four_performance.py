"""G4 reporting uses actual quantities and a separate prospective ledger."""
from generation_four_paper_tracker import FILE_STEM, IDS
from strategies import generation_four as g4
from reporting.generation_one_performance import calculate_generation_one

def calculate_generation_four(root,day,cutoff,marks,quote_for):
    return calculate_generation_one(root,day,cutoff,marks,quote_for,
        file_stem=FILE_STEM,ids=IDS,flash_catalog=g4,minute_catalog=g4.MINUTE_CATALOG,
        engine_name='generation_four_bidask_independent')
