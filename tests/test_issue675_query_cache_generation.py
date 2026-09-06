import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tools.timeline_materializer as tm


class Issue675QueryCacheGenerationTests(unittest.TestCase):
    @staticmethod
    def _payload(generated_at: str, event_id: str, title: str) -> dict:
        event = {
            "id": event_id,
            "source_type": "VAULT_MEMORY",
            "authority": "DERIVED_MEMORY_HISTORY",
            "event_at": generated_at,
            "recorded_at": generated_at,
            "title": title,
            "summary": title,
            "text": title,
            "project": "lowvram",
            "refs": [],
            "anchors": [f"memory:{event_id}"],
        }
        return {
            "schema": tm.SCHEMA,
            "generated_at": generated_at,
            "horizon_days": 30,
            "timeline": {
                "schema_version": 3,
                "authority": "DERIVED_HISTORY_ONLY",
                "contract": {},
                "events": [event],
                "historical_evidence_events": [],
                "continuity_graph": {"cases": [], "summary": {}},
                "work_graph": {},
            },
        }

    def test_correction_published_mid_query_is_not_cached_under_new_store_generation(self):
        with tempfile.TemporaryDirectory(prefix="issue675-cache-generation-") as raw:
            root = Path(raw)
            state = root / ".state" / "timeline"
            state.mkdir(parents=True)
            store = state / tm.STORE_PATH.name
            old = self._payload(
                "2026-09-06T08:00:00+00:00",
                "mem:old-front-axis",
                "front axis diagnosis says camera is wrong",
            )
            correction = self._payload(
                "2026-09-06T08:05:00+00:00",
                "mem:front-axis-correction",
                "front axis diagnosis retracted camera was not wrong corrected evidence",
            )
            store.write_text(json.dumps(old), encoding="utf-8")

            real_load = tm.load_materialized

            def publish_correction_during_old_read(*, root: Path = root):
                # Model refresh publication after the query captured its initial
                # generation token but while it is still computing from old data.
                store.write_text(json.dumps(correction), encoding="utf-8")
                return old

            with patch.object(tm, "load_materialized", side_effect=publish_correction_during_old_read):
                first = tm.query_materialized(root=root, query="front axis diagnosis", limit=8)

            self.assertEqual(first["events"][0]["id"], "mem:old-front-axis")

            # Next healthy read sees the corrected canonical store. It must not
            # accept a cache entry computed from the old payload but mislabeled
            # with the new generation token.
            with patch.object(tm, "load_materialized", wraps=real_load) as load:
                second = tm.query_materialized(root=root, query="front axis diagnosis", limit=8)

            self.assertEqual(second["events"][0]["id"], "mem:front-axis-correction")
            self.assertFalse(second.get("query_cache", {}).get("used", False))
            self.assertGreaterEqual(load.call_count, 1)


if __name__ == "__main__":
    unittest.main()
