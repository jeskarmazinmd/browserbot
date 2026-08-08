import json
import tempfile
import unittest
from pathlib import Path

from research_lab.discovery import build_report, discover_strategies
from research_lab.models import (
    FieldProvenance,
    TemporalClass,
)
from research_lab.plugins import PluginRegistry
from research_lab.provenance import infer_field, safe_for_entry


class ResearchLabTests(unittest.TestCase):
    def test_strategy_discovery_does_not_import_module(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            folder=root/"strategies"
            folder.mkdir()
            (folder/"strategy_x.py").write_text(
                'import definitely_missing_dependency\n'
                'STRATEGY_ID="X"\n'
                'FAMILY="TEST"\n'
                'PAPER_ONLY=True\n'
                'CONFIG={"threshold": 1.25}\n'
            )
            found=discover_strategies(root)
            self.assertEqual(len(found),1)
            self.assertEqual(found[0].strategy_id,"X")
            self.assertEqual(found[0].config["threshold"],1.25)

    def test_nested_research_metrics_are_discovered(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            (root/"strategies").mkdir()
            data=root/"data"
            data.mkdir()
            (data/"signal_paper_outcomes_test.jsonl").write_text(
                json.dumps({
                    "strategy_id":"X",
                    "research_metrics":{
                        "rebound_2m_pct":0.4,
                        "nested":{"shape":2.0},
                    },
                    "ret_pct":0.5,
                })+"\n"
            )
            report=build_report(root,data)
            fields=set(report.sources[0].fields)
            self.assertIn("research_metrics.rebound_2m_pct",fields)
            self.assertIn("research_metrics.nested.shape",fields)

    def test_future_information_is_not_entry_safe(self):
        self.assertEqual(
            infer_field("exit_price").temporal_class,
            TemporalClass.POST_ENTRY,
        )
        self.assertFalse(safe_for_entry("mfe_pct"))
        self.assertTrue(safe_for_entry("research_metrics.rebound_2m_pct"))


    def test_capabilities_distinguish_tightening_from_loosening(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            (root/"strategies").mkdir()
            data=root/"data"
            data.mkdir()

            (data/"signal_paper_outcomes_x.jsonl").write_text(
                json.dumps({
                    "strategy_id":"X",
                    "symbol":"XYZ",
                    "signal_timestamp":"2026-08-08T14:00:00+00:00",
                    "research_metrics":{"strength":1.2},
                    "ret_pct":0.5,
                })+"\n"
            )

            report=build_report(root,data)
            caps={x.name:x.state.value for x in report.capabilities}

            self.assertEqual(
                caps["tighten_existing_filters"],
                "AVAILABLE",
            )
            self.assertEqual(
                caps["loosen_or_remove_filters"],
                "PROSPECTIVE_ONLY",
            )

    def test_provenance_can_be_extended_by_plugin(self):
        from research_lab.plugins import REGISTRY

        field_name="future_custom_entry_metric_for_test"

        def rule(field):
            if field==field_name:
                return FieldProvenance(
                    field,
                    TemporalClass.ENTRY_KNOWN,
                    "test plugin",
                    confidence="explicit",
                )
            return None

        REGISTRY.register(
            "provenance_rule",
            "unit_test_custom_metric",
            rule,
        )

        self.assertTrue(safe_for_entry(field_name))


    def test_research_memory_has_stable_identity_and_no_duplicates(self):
        from research_lab.memory import ResearchMemory

        with tempfile.TemporaryDirectory() as root:
            memory=ResearchMemory(Path(root)/"memory.jsonl")

            row=memory.record(
                "M1",
                "threshold_tightening",
                {"metric":"rebound_2m_pct","value":0.3},
                status="INCONCLUSIVE",
            )

            self.assertEqual(len(memory.load()),1)

            with self.assertRaises(ValueError):
                memory.record(
                    "M1",
                    "threshold_tightening",
                    {"value":0.3,"metric":"rebound_2m_pct"},
                    status="INCONCLUSIVE",
                )

            self.assertTrue(row["hypothesis_id"])

    def test_search_coverage_distinguishes_ready_from_searched(self):
        from research_lab.memory import ResearchMemory
        from research_lab.search_space import coverage

        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            (root/"strategies").mkdir()
            data=root/"data"
            data.mkdir()

            (data/"signal_paper_outcomes_x.jsonl").write_text(
                json.dumps({
                    "strategy_id":"X",
                    "symbol":"XYZ",
                    "signal_timestamp":"2026-08-08T14:00:00+00:00",
                    "research_metrics":{"strength":1.2},
                    "ret_pct":0.5,
                })+"\n"
            )

            report=build_report(root,data)
            memory=ResearchMemory(root/"memory.jsonl")

            before={
                x.dimension.name:x
                for x in coverage(report.capabilities,memory.load())
            }

            self.assertEqual(
                before["threshold_tightening"].readiness,
                "READY",
            )
            self.assertEqual(
                before["threshold_tightening"].attempts,
                0,
            )

            memory.record(
                "X",
                "threshold_tightening",
                {"metric":"strength","value":1.3},
                status="TESTED",
            )

            after={
                x.dimension.name:x
                for x in coverage(report.capabilities,memory.load())
            }

            self.assertEqual(
                after["threshold_tightening"].attempts,
                1,
            )
            self.assertEqual(
                after["threshold_tightening"].strategies_touched,
                1,
            )


    def test_hypothesis_generation_is_broad_and_entry_safe(self):
        from research_lab.features import profile_sources
        from research_lab.hypotheses import generate_proposals

        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            folder=root/"strategies"
            folder.mkdir()
            data=root/"data"
            data.mkdir()

            (folder/"strategy_x.py").write_text(
                'STRATEGY_ID="X"\n'
                'PAPER_ONLY=True\n'
                'CONFIG={"min_strength":1.0,"stop_loss_fraction":0.02}\n'
                'EXIT_MODEL="c1"\n'
            )

            lines=[]
            for i in range(40):
                lines.append(json.dumps({
                    "strategy_id":"X",
                    "symbol":f"S{i}",
                    "signal_timestamp":"2026-08-08T14:00:00+00:00",
                    "research_metrics":{
                        "strength":float(i),
                        "shape":float(i%7),
                    },
                    "mfe_pct":99.0,
                    "ret_pct":1.0 if i%2 else -1.0,
                }))

            (data/"signal_paper_outcomes_x.jsonl").write_text(
                chr(10).join(lines)+chr(10)
            )

            report=build_report(root,data)
            profiles=profile_sources(report.sources)
            proposals=generate_proposals(report.strategies,profiles)

            generators={x.generator for x in proposals}
            self.assertIn("parameter_neighborhood",generators)
            self.assertIn("source_ablation",generators)
            self.assertIn("entry_feature_thresholds",generators)
            self.assertIn("pair_transforms",generators)

            serialized=" ".join(
                repr(x.specification)
                for x in proposals
            )
            self.assertNotIn("mfe_pct",serialized)

    def test_hypothesis_generators_are_plugin_extensible(self):
        from research_lab.hypotheses import generate_proposals
        from research_lab.models import HypothesisProposal
        from research_lab.plugins import REGISTRY

        def generator(context):
            return [HypothesisProposal(
                "X",
                "behavioral_novelty",
                "unit_test_generator",
                {"operator":"novel_test"},
                "test extension",
            )]

        REGISTRY.register(
            "hypothesis_generator",
            "unit_test_generator",
            generator,
        )

        generated=generate_proposals([],[])
        self.assertTrue(
            any(x.generator=="unit_test_generator" for x in generated)
        )

    def test_entry_timestamp_is_entry_safe(self):
        from research_lab.provenance import safe_for_entry
        self.assertTrue(safe_for_entry("entry_timestamp"))

    def test_dynamic_outcome_state_is_never_entry_safe(self):
        from research_lab.provenance import safe_for_entry
        for field in (
            "highest_price",
            "activated",
            "activation_time",
            "recent_samples",
            "checkpoint_evaluated",
            "last_observed_price",
        ):
            with self.subTest(field=field):
                self.assertFalse(safe_for_entry(field))

    def test_evidence_index_joins_only_prior_regime(self):
        from datetime import datetime,timezone
        from research_lab.evidence import EvidenceIndex,RegimeEvidence,TradeEvidence

        regime=RegimeEvidence(
            datetime(2026,8,3,14,0,tzinfo=timezone.utc),
            {"regime.trend.classification":"UP"},
            "regime.jsonl",
        )
        trade=TradeEvidence(
            "S","XYZ","S|XYZ",
            datetime(2026,8,3,14,5,tzinfo=timezone.utc),
            datetime(2026,8,3,14,5,tzinfo=timezone.utc),
            1.0,
        )
        index=EvidenceIndex((trade,),(regime,),())
        self.assertEqual(
            index.regime_at(trade.entry_time).fields[
                "regime.trend.classification"
            ],
            "UP",
        )
        self.assertIsNone(
            index.regime_at(
                datetime(2026,8,3,13,59,tzinfo=timezone.utc)
            )
        )

    def test_evidence_index_detects_matched_siblings(self):
        from datetime import datetime,timezone
        from research_lab.evidence import EvidenceIndex,TradeEvidence

        now=datetime(2026,8,3,14,0,tzinfo=timezone.utc)
        trades=(
            TradeEvidence("C1","XYZ","C1|XYZ",now,now,1.0,"B"),
            TradeEvidence("C2","XYZ","C2|XYZ",now,now,2.0,"B"),
        )
        index=EvidenceIndex(trades,(),())
        self.assertEqual(len(index.coincident_groups()),1)
        self.assertEqual(len(index.controlled_sibling_groups()),1)
        self.assertEqual(
            index.controlled_sibling_overlap_counts()[("C1","C2")],
            1,
        )

    def test_broad_generators_span_multiple_research_classes(self):
        from datetime import datetime,timedelta,timezone
        from research_lab.broad_hypotheses import generate_broad_proposals
        from research_lab.evidence import EvidenceIndex,RegimeEvidence,TradeEvidence
        from research_lab.features import FeatureProfile

        start=datetime(2026,8,3,14,0,tzinfo=timezone.utc)
        trades=[]
        regimes=[]

        for minute in range(5):
            timestamp=start+timedelta(minutes=minute)
            regimes.append(RegimeEvidence(
                timestamp,
                {"regime.returns.SPY.5m":float(minute)/10.0},
                "regime.jsonl",
            ))
            for n in range(8):
                trades.append(TradeEvidence(
                    "TEST",
                    f"XYZ{n}",
                    f"TEST|{minute}|{n}",
                    timestamp,
                    timestamp,
                    1.0 if n%2 else -1.0,
                ))

        evidence=EvidenceIndex(tuple(trades),tuple(regimes),())

        profiles=[]
        for name in ("alpha","beta","gamma"):
            profiles.append(FeatureProfile(
                strategy_id="TEST",
                field=name,
                kind="numeric",
                count=40,
                unique_count=40,
                numeric_quantiles={
                    "q10":1.0,"q20":2.0,"q40":4.0,
                    "q50":5.0,"q60":6.0,"q80":8.0,"q90":9.0,
                },
                outcomes=40,
            ))

        proposals=generate_broad_proposals([],profiles,evidence)
        dimensions={x.dimension for x in proposals}

        expected={
            "range_and_band_rules",
            "pairwise_interactions",
            "higher_order_interactions",
            "time_of_day",
            "market_direction_context",
            "winner_cohort_mining",
            "failure_mode_mining",
            "loser_rescue",
            "signal_sequence_and_waves",
        }

        self.assertTrue(expected<=dimensions,expected-dimensions)

    def test_plugin_registry_is_open_ended(self):
        r=PluginRegistry()
        marker=object()
        r.register("future_new_kind","example",marker)
        self.assertIs(r.get("future_new_kind","example"),marker)


if __name__=="__main__":
    unittest.main()
