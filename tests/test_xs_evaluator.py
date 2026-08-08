import unittest

import numpy as np
import pandas as pd

from research_lab.xs_evaluator import (
    XSEvaluationPolicy,
    evaluate_scored_predictions,
    select_opportunities,
)


def scored_frame(days=4, minutes=40, realized=0.003):
    rows=[]
    start=pd.Timestamp("2026-08-10 13:30:00+00:00")
    for day in range(days):
        base=start+pd.Timedelta(days=day)
        for minute in range(minutes):
            when=base+pd.Timedelta(minutes=minute)
            for rank,target in enumerate(("A","B","C")):
                rows.append({
                    "decision_time":when,
                    "target":target,
                    "predicted_return":0.004-rank*0.001,
                    "realized_return":realized-rank*0.0002,
                })
    return pd.DataFrame(rows)


class XSEvaluatorTests(unittest.TestCase):
    birth="2026-08-10 13:30:00+00:00"

    def test_selection_does_not_depend_on_realized_returns(self):
        frame=scored_frame(days=1,minutes=5)
        policy=XSEvaluationPolicy(
            min_prediction_bps=1,
            max_opportunities_per_minute=1,
        )
        original=select_opportunities(frame,policy)

        changed=frame.copy()
        rng=np.random.default_rng(7)
        changed["realized_return"]=rng.normal(0,10,len(changed))
        mutated=select_opportunities(changed,policy)

        self.assertEqual(list(original["target"]),list(mutated["target"]))
        self.assertEqual(
            list(original["decision_time"]),
            list(mutated["decision_time"]),
        )

    def test_cost_and_evidence_gates_allow_strong_multiday_candidate(self):
        policy=XSEvaluationPolicy(
            min_prediction_bps=1,
            max_opportunities_per_minute=1,
            primary_cost_bps=10,
            min_trades=100,
            min_days=3,
        )
        result=evaluate_scored_predictions(
            scored_frame(),policy,born_at=self.birth
        )
        self.assertTrue(result.paper_candidate)
        self.assertEqual(result.trades,160)
        self.assertEqual(result.days,4)
        self.assertGreater(result.primary_lower_confidence_bps,0)

    def test_apparent_edge_fails_when_execution_cost_exceeds_return(self):
        policy=XSEvaluationPolicy(
            min_prediction_bps=1,
            max_opportunities_per_minute=1,
            primary_cost_bps=10,
            min_trades=1,
            min_days=1,
            min_positive_day_fraction=0,
        )
        result=evaluate_scored_predictions(
            scored_frame(days=2,minutes=5,realized=0.0005),
            policy,
            born_at=self.birth,
        )
        self.assertFalse(result.paper_candidate)
        self.assertLess(result.primary_net_mean_bps,0)

    def test_small_sample_never_becomes_paper_candidate(self):
        policy=XSEvaluationPolicy(
            min_prediction_bps=1,
            max_opportunities_per_minute=1,
            primary_cost_bps=0,
            min_trades=100,
            min_days=3,
        )
        result=evaluate_scored_predictions(
            scored_frame(days=1,minutes=10),
            policy,
            born_at=self.birth,
        )
        self.assertFalse(result.paper_candidate)
        self.assertIn("trades",result.reason)
        self.assertIn("days",result.reason)

    def test_prebirth_results_are_never_counted(self):
        frame=scored_frame(days=4,minutes=40)
        result=evaluate_scored_predictions(
            frame,
            XSEvaluationPolicy(
                min_prediction_bps=1,
                max_opportunities_per_minute=1,
                min_trades=1,
                min_days=1,
            ),
            born_at="2026-08-12 13:30:00+00:00",
        )
        self.assertEqual(result.days,2)
        self.assertEqual(result.trades,80)


if __name__=="__main__":
    unittest.main()
