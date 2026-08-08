import unittest
from datetime import datetime,timezone
from types import SimpleNamespace

from research_lab.family_analyst import (
    analyze_parent,
    retirement_watchlist,
    screen_accepted_subset,
)


def trade(strategy,outcome,field,day=6):
    return SimpleNamespace(
        strategy_id=strategy,
        outcome_pct=outcome,
        entry_time=datetime(2026,8,day,14,tzinfo=timezone.utc),
        safe_fields={"quality":field},
    )


def proposal(strategy,dimension,operator="<=",**extra):
    specification={"operator":operator,**extra}
    return SimpleNamespace(
        strategy_id=strategy,
        dimension=dimension,
        generator="test_generator",
        specification=specification,
        rationale="test idea",
        historical_testability="HISTORICAL_ACCEPTED_SUBSET",
    )


class Evidence:
    def __init__(self,trades):
        self._trades=trades

    def trades_by_strategy(self):
        result={}
        for item in self._trades:
            result.setdefault(item.strategy_id,[]).append(item)
        return result


class FamilyAnalystTests(unittest.TestCase):
    def test_entry_known_subset_can_be_screened_without_post_entry_data(self):
        trades=[
            trade("P",1.0 if i<30 else -1.0,i,6 if i%2==0 else 7)
            for i in range(60)
        ]
        item=proposal(
            "P","univariate_new_features",field="quality",threshold=29
        )
        screen=screen_accepted_subset(item,trades,min_trades=20)
        self.assertTrue(screen.supported)
        self.assertEqual(screen.trades,30)
        self.assertGreater(screen.uplift_pct_points,0)

    def test_capital_simulator_drives_primary_subset_score_when_available(self):
        trades=[
            trade("P",1.0 if i<30 else -1.0,i,6 if i%2==0 else 7)
            for i in range(60)
        ]
        item=proposal(
            "P","univariate_new_features",field="quality",threshold=29
        )

        def simulate(items):
            return SimpleNamespace(
                end_equity=5000*(1+sum(x.outcome_pct for x in items)/100)
            )

        screen=screen_accepted_subset(
            item,trades,min_trades=20,capital_simulator=simulate
        )
        self.assertIsNotNone(screen.capital_compound_return_pct)
        self.assertIsNotNone(screen.capital_uplift_pct_points)

    def test_path_dependent_idea_stays_exploratory(self):
        trades=[trade("C2",.1,i) for i in range(40)]
        item=proposal("C2","stop_geometry",operator="replace_exit_model")
        screen=screen_accepted_subset(item,trades)
        self.assertFalse(screen.supported)
        self.assertIsNone(screen.score)

    def test_shortlist_keeps_empirical_and_exploratory_lanes(self):
        trades=[
            trade("G",1.0 if i<30 else -1.0,i,6 if i%2==0 else 7)
            for i in range(60)
        ]
        proposals=[
            proposal("G","univariate_new_features",field="quality",threshold=29),
            proposal("G","time_of_day",operator="replace_exit_model"),
            proposal("G","stop_geometry",operator="replace_exit_model"),
        ]
        ideas=analyze_parent("G",proposals,Evidence(trades),show=3,min_trades=20)
        self.assertIn("EMPIRICAL",{x.lane for x in ideas})
        self.assertIn("EXPLORATORY",{x.lane for x in ideas})

    def test_retirement_watchlist_is_advisory_consistent_loser_screen(self):
        rows=[]
        for day in (6,7):
            rows.extend(trade("BAD",-.2,i,day) for i in range(60))
            rows.extend(trade("MIXED",-.2 if day==6 else .3,i,day) for i in range(60))
        result=retirement_watchlist(Evidence(rows),min_trades=100,min_days=2)
        ids={row[1] for row in result}
        self.assertIn("BAD",ids)
        self.assertNotIn("MIXED",ids)

    def test_capital_retirement_screen_overrides_raw_trade_means(self):
        rows=[trade("J6",-.2,i,6 if i<60 else 7) for i in range(120)]
        capital={
            ("2026-08-06","J6"):SimpleNamespace(
                strategy_id="J6",signals=60,end_equity=5050
            ),
            ("2026-08-07","J6"):SimpleNamespace(
                strategy_id="J6",signals=60,end_equity=5050
            ),
        }
        result=retirement_watchlist(
            Evidence(rows),min_trades=100,min_days=2,capital_results=capital
        )
        self.assertNotIn("J6",{row[1] for row in result})


if __name__=="__main__":
    unittest.main()
