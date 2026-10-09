"""Required focused G6 and affected-engine regressions, standard library only.

The pre-existing microstructure10 definition-count test fails identically on
cf7b7f77 (expects ten active workers after nine were pruned). It is preserved
unchanged and documented separately, rather than weakening its assertion.
"""
import unittest
MODULES=[
 'tests.test_generation_six','tests.test_generation_one','tests.test_generation_two',
 'tests.test_generation_three','tests.test_generation_four','tests.test_generation_five',
 'tests.test_g6_evidence_export','tests.test_all_engine_performance','tests.test_output_switches',
 'tests.test_statarb2','tests.test_forex10','tests.test_short10',
 'tests.test_performance_pruning_dependencies','tests.test_independent_bidask_tracker',
 'tests.test_independent_multi_leg_bidask','tests.test_bidask_multi_leg_paper_tracker',
 'tests.test_bidask_paper_outcome_tracker','tests.test_capital_performance','tests.test_g3_native_audit',
 'tests.test_microstructure_shadow_wiring','tests.test_statarb_shadow_wiring',
 'tests.test_forex_shadow_wiring','tests.test_short_shadow_wiring',
]
if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromNames(MODULES)
 result=unittest.TextTestRunner(verbosity=1).run(suite)
 raise SystemExit(not result.wasSuccessful())
