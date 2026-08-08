import unittest

import pandas as pd

from research_lab.xs_evaluator import XSEvaluationPolicy
from research_lab.xs_lifecycle import (
    evaluate_family,
    new_experiment,
)


def evidence(start, mean_return, days=4, minutes=40):
    rows=[]
    base=pd.Timestamp(start)
    for day in range(days):
        for minute in range(minutes):
            rows.append({
                "decision_time":base+pd.Timedelta(days=day,minutes=minute),
                "target":"XYZ",
                "predicted_return":0.003,
                "realized_return":mean_return,
            })
    return pd.DataFrame(rows)


class XSLifecycleTests(unittest.TestCase):
    def policy(self):
        return XSEvaluationPolicy(
            min_prediction_bps=1,
            max_opportunities_per_minute=1,
            primary_cost_bps=10,
            min_trades=100,
            min_days=3,
        )

    def test_experiment_identity_is_stable_but_birth_is_explicit(self):
        spec={"lookback":60,"top_k":3}
        a=new_experiment("XS_LEAD_LAG",spec,born_at="2026-08-10T13:30:00Z")
        b=new_experiment("XS_LEAD_LAG",spec,born_at="2026-08-11T13:30:00Z")
        self.assertEqual(a.experiment_id,b.experiment_id)
        self.assertNotEqual(a.born_at,b.born_at)

    def test_prebirth_good_history_cannot_rescue_bad_forward_results(self):
        experiment=new_experiment(
            "XS_LEAD_LAG",{},born_at="2026-08-12T13:30:00Z"
        )
        old=evidence("2026-08-10T13:30:00Z",0.01,days=2)
        forward=evidence("2026-08-12T13:30:00Z",-0.002,days=4)
        scored=pd.concat([old,forward],ignore_index=True)
        result=evaluate_family(
            [experiment],
            {experiment.experiment_id:scored},
            self.policy(),
        )[0]
        self.assertEqual(result.state,"HOLD")
        self.assertFalse(result.adjusted_significant)

    def test_strong_forward_experiment_can_become_expand_eligible(self):
        experiment=new_experiment(
            "XS_LEAD_LAG",{},born_at="2026-08-10T13:30:00Z"
        )
        result=evaluate_family(
            [experiment],
            {experiment.experiment_id:evidence(
                "2026-08-10T13:30:00Z",0.003
            )},
            self.policy(),
        )[0]
        self.assertEqual(result.state,"EXPAND_ELIGIBLE")
        self.assertTrue(result.adjusted_significant)

    def test_no_lifecycle_decision_disables_runtime(self):
        experiment=new_experiment(
            "XS_LEAD_LAG",{},born_at="2026-08-10T13:30:00Z"
        )
        result=evaluate_family(
            [experiment],
            {experiment.experiment_id:evidence(
                "2026-08-10T13:30:00Z",-0.01
            )},
            self.policy(),
        )[0]
        self.assertNotIn("DISABLE",result.state)
        self.assertNotIn("RETIRE",result.state)


if __name__=="__main__":
    unittest.main()
