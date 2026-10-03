"""G2 actual-fill performance with isolated births and ledger."""
from generation_two_paper_tracker import FILE_STEM, IDS
from strategies import generation_two
from reporting.generation_one_performance import calculate_generation_one


def calculate_generation_two(root, day, cutoff, marks, quote_for):
    return calculate_generation_one(
        root, day, cutoff, marks, quote_for, file_stem=FILE_STEM, ids=IDS,
        flash_catalog=generation_two, minute_catalog=None,
        engine_name="generation_two_bidask_independent",
    )
