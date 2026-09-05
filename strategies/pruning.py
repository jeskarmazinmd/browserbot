"""Central, reversible registry of retired prospective strategy outputs.

These IDs were reviewed against their complete fixed-cutoff daily histories
through 2026-09-04.  Retirement stops new output and active ranking only; it
does not delete modules, market-data collection, or historical outcomes.
"""

PRUNED_OUTPUT_STRATEGY_IDS = frozenset({
    "BO1", "BRK30", "C1F1MID", "C1T9", "C3N25A50", "C3N30",
    "CMDMIN1", "COMPX1", "CSBREADTH1INV", "CSDISP1INV", "CSOPEN1",
    "CSRANK20INV", "CSRANK5INV", "CSRELSPY1INV", "CSREV1INV",
    "CSVOLADJ1", "EMA1", "EMA2", "ENTROPY1", "EVTSEC8K1INV",
    "EVTVOL1INV", "FUTMES1", "FUTMGCR1", "FUTMNQ1", "FXLON1",
    "GP1", "LEADBASK1", "LEADBASK2", "M3", "MIDREV1",
    "MKTNEUT1", "MSBIDPULL1", "MSDEPTH1", "MSFLIP1", "MSIMB1",
    "MSPERSIST1", "MSRECOV1", "MSVEL1", "O", "OPTDIR1INV",
    "OPTDIR2INV", "OPTVERT1INV", "OPTVERT2INV", "OR1",
    "PEERBASK1", "PULLCONT1", "QMID", "SECTORH1", "SECTORROT1",
    "SHTBRD1", "SHTFAIL1", "SHTGAP1", "SHTVOL1", "SMA1",
    "SPY_ENS1", "SPY_MOM1", "SPY_MR1", "STBETA1", "STBREAK1",
    "STCINT2", "STPAIR1", "VT1", "VWEMA1",
})

# These are deliberately outside the performance-pruning mechanism.  Some
# produce signals consumed by successful descendants; others are the live or
# parity paths currently under execution study.
DEPENDENCY_PROTECTED_STRATEGY_IDS = frozenset({
    "A", "B", "D", "H", "M2", "C3N25S10", "C3N25S10DUP",
    "C3N25S10NH015", "C3N25S10NH015DUP",
})

assert PRUNED_OUTPUT_STRATEGY_IDS.isdisjoint(DEPENDENCY_PROTECTED_STRATEGY_IDS)


def output_is_pruned(strategy_id):
    return str(strategy_id or "").upper() in PRUNED_OUTPUT_STRATEGY_IDS


def active_output_ids(strategy_ids):
    """Preserve order while removing only retired output IDs."""
    return tuple(sid for sid in strategy_ids if not output_is_pruned(sid))
