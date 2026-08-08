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

    def test_plugin_registry_is_open_ended(self):
        r=PluginRegistry()
        marker=object()
        r.register("future_new_kind","example",marker)
        self.assertIs(r.get("future_new_kind","example"),marker)


if __name__=="__main__":
    unittest.main()
