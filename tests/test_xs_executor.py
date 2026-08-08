import unittest

import numpy as np
import pandas as pd

from research_lab.xs_adaptive import generate_predictions
from research_lab.xs_executor import generate_shared_predictions
from research_lab.xs_shadows import ready_shadow_specs


def market(rows=95,symbols=7):
    rng=np.random.default_rng(123)
    base=rng.normal(0,0.002,(rows,symbols))
    # Give the selector real lead/lag structure rather than pure noise.
    base[1:,1]=0.85*base[:-1,0]+0.15*base[1:,1]
    frame=pd.DataFrame(
        base,
        columns=[f"S{i}" for i in range(symbols)],
        index=pd.date_range(
            "2026-08-10 13:30:00+00:00",periods=rows,freq="min"
        ),
    )
    return 100*(1+frame).cumprod()


class XSExecutorTests(unittest.TestCase):
    def test_shared_executor_matches_independent_predictions(self):
        prices=market()
        specs=tuple(
            x for x in ready_shadow_specs()
            if x.name in {"LL60H1K1","LL60H1K3","LL60LOOSE","LL60STRICT"}
        )
        shared,telemetry=generate_shared_predictions(prices,specs)

        for spec in specs:
            expected=generate_predictions(prices,spec.config)
            actual=shared[shared["shadow_name"]==spec.name]
            cols=[
                "decision_time","target","predicted_return","leaders",
                "correlations","relationship_selected_at",
            ]
            pd.testing.assert_frame_equal(
                actual[cols].reset_index(drop=True),
                expected.sort_values(
                    ["decision_time","target"],kind="mergesort"
                )[cols].reset_index(drop=True),
                check_exact=False,
                rtol=1e-12,
                atol=1e-15,
            )
        self.assertGreater(telemetry.fits_avoided,0)

    def test_executor_never_attaches_realized_outcomes(self):
        predictions,_=generate_shared_predictions(market())
        self.assertNotIn("realized_return",predictions.columns)

    def test_sharing_reduces_fit_count_for_default_population(self):
        _,telemetry=generate_shared_predictions(market(rows=150))
        self.assertGreater(
            telemetry.equivalent_independent_fit_calls,
            telemetry.shared_fit_calls,
        )
        self.assertGreater(telemetry.fits_avoided,0)


if __name__=="__main__":
    unittest.main()
