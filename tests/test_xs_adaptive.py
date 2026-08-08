import unittest

import numpy as np
import pandas as pd

from research_lab.xs_adaptive import (
    AdaptiveXSConfig,
    generate_predictions,
    score_predictions,
)


def synthetic_prices(rows=140):
    rng=np.random.default_rng(42)
    a=rng.normal(0,0.002,rows)
    b=rng.normal(0,0.002,rows)
    y=np.zeros(rows)
    for i in range(1,rows):
        source=a[i-1] if i < rows//2 else b[i-1]
        y[i]=0.9*source
    returns=pd.DataFrame(
        {"A":a,"B":b,"Y":y},
        index=pd.date_range(
            "2026-08-10 13:30:00+00:00",
            periods=rows,
            freq="min",
        ),
    )
    return 100.0*(1.0+returns).cumprod()


class AdaptiveXSTests(unittest.TestCase):
    def config(self):
        return AdaptiveXSConfig(
            lookback_minutes=25,
            horizon_minutes=1,
            refresh_minutes=5,
            top_k=1,
            min_abs_correlation=0.50,
            min_observations=20,
            false_discovery_rate=1.0,
        )

    def test_relationships_can_change_over_time(self):
        prices=synthetic_prices()
        predictions=generate_predictions(prices,self.config())
        y=predictions[predictions["target"]=="Y"]
        early=y.iloc[:20]
        late=y.iloc[-20:]
        self.assertTrue(any("A" in leaders for leaders in early["leaders"]))
        self.assertTrue(any("B" in leaders for leaders in late["leaders"]))

    def test_future_mutation_cannot_change_earlier_predictions(self):
        prices=synthetic_prices()
        cutoff=prices.index[85]
        original=generate_predictions(prices,self.config())

        mutated=prices.copy()
        mutated.loc[mutated.index > cutoff,"Y"] *= 1.75
        mutated.loc[mutated.index > cutoff,"A"] *= 0.60
        mutated.loc[mutated.index > cutoff,"B"] *= 1.40
        changed=generate_predictions(mutated,self.config())

        cols=[
            "decision_time","target","predicted_return",
            "leaders","correlations","relationship_selected_at",
        ]
        left=original[original["decision_time"] <= cutoff][cols]
        right=changed[changed["decision_time"] <= cutoff][cols]
        pd.testing.assert_frame_equal(
            left.reset_index(drop=True),
            right.reset_index(drop=True),
        )

    def test_scoring_is_separate_from_prediction_generation(self):
        prices=synthetic_prices()
        predictions=generate_predictions(prices,self.config())
        self.assertNotIn("realized_return",predictions.columns)
        scored=score_predictions(predictions,prices,1)
        self.assertIn("realized_return",scored.columns)


if __name__=="__main__":
    unittest.main()
