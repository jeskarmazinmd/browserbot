import unittest

from research_lab.xs_shadows import (
    RESEARCH_LANES,
    activate,
    compute_plan,
    ready_shadow_specs,
    seed_shadow_specs,
    shared_fit_groups,
)


class XSShadowTests(unittest.TestCase):
    def test_broad_research_lanes_remain_visible(self):
        specs=seed_shadow_specs()
        self.assertEqual(
            {x.dimension for x in specs},
            set(RESEARCH_LANES),
        )
        self.assertEqual(len(ready_shadow_specs(specs)),10)
        self.assertTrue(all(
            x.state=="PLANNED"
            for x in specs
            if x.dimension!="cross_symbol_lead_lag"
        ))

    def test_variants_share_expensive_fit_groups(self):
        ready=ready_shadow_specs()
        groups=shared_fit_groups(ready)
        self.assertLess(len(groups),len(ready))
        group_sizes=sorted(len(x) for x in groups.values())
        self.assertGreater(max(group_sizes),1)

    def test_current_universe_fits_initial_memory_budget(self):
        plan=compute_plan(2684)
        self.assertTrue(plan.allowed,plan.reason)
        self.assertEqual(plan.shadow_experiments,10)
        self.assertLess(plan.estimated_peak_fit_mib,256)

    def test_compute_budget_fails_closed(self):
        plan=compute_plan(10000)
        self.assertFalse(plan.allowed)
        self.assertIn("working-set budget",plan.reason)

    def test_activation_excludes_unimplemented_lanes_and_freezes_birth(self):
        birth="2026-08-10T13:30:00+00:00"
        experiments=activate(born_at=birth)
        self.assertEqual(len(experiments),10)
        self.assertTrue(all(x.born_at==birth for x in experiments))
        self.assertTrue(all(
            x.family=="cross_symbol_lead_lag"
            for x in experiments
        ))


if __name__=="__main__":
    unittest.main()
