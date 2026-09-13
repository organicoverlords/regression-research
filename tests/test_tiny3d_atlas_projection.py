import json
import tempfile
import unittest
from pathlib import Path

from tools.tiny3d_atlas_projection import CACHE_RELATIVE, SHOWROOM_RELATIVE, project_current


class Tiny3DAtlasProjectionTests(unittest.TestCase):
    def _fixture(self, root: Path):
        asset_id = "a" * 64
        asset_dir = root / asset_id
        asset_dir.mkdir(parents=True)
        mesh = asset_dir / "portable" / "asset.glb"
        mesh.parent.mkdir(parents=True)
        mesh.write_bytes(b"glb-current")
        record = {
            "asset_id": asset_id,
            "directory_name": asset_id,
            "display_name": "Character Angular Android Blade Herald",
            "search_aliases": ["basalt ferns", "Nature Mossige Basaltkivet Ja Saniaiset"],
            "asset_dir": str(asset_dir),
            "proof": {
                "strongest_state": "TINY3D_VERIFIED",
                "states": {"P3_RUNTIME_PROVEN": False},
                "latest_visual_proof": None,
                "reviewed_visual_proof": [],
                "metadata_gaps": [],
            },
            "actions": {"inspect": ["tiny3d", "library", "show", asset_id, "--workspace", str(root)]},
        }
        stat = mesh.stat()
        cache = {
            "schema": "tinylab.asset-library-cache.v1",
            "entries": {
                asset_id: {
                    "signature": [
                        {"path": "portable/asset.glb", "exists": True, "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}
                    ],
                    "record": record,
                }
            },
        }
        showroom = {
            "schema": "tiny3d.showroom-v2-catalog.v1",
            "assets": [
                {
                    "tiny3d_asset_ids": [asset_id],
                    "logical_id": "mesh:" + "b" * 64,
                    "display_name": "Character Angular Android Blade Herald",
                    "catalog_state": "TINY3D_LIBRARY_LINKED",
                    "zone": "LegacyReview",
                }
            ],
        }
        cache_path = root / CACHE_RELATIVE
        showroom_path = root / SHOWROOM_RELATIVE
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache), encoding="utf-8")
        showroom_path.write_text(json.dumps(showroom), encoding="utf-8")
        return asset_id, mesh, cache_path, showroom_path

    def test_current_signature_projects_android_showroom_and_fail_closed_proof_fields(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            asset_id, _, cache_path, showroom_path = self._fixture(root)
            before = (cache_path.read_bytes(), showroom_path.read_bytes())
            result = project_current("android", root)
            self.assertEqual(result["count"], 1)
            entry = result["entries"][0]
            self.assertEqual(entry["asset_id"], asset_id)
            self.assertEqual(entry["cache_freshness"]["state"], "CURRENT_SIGNATURE_MATCH")
            self.assertEqual(entry["showroom"]["state"], "LINKED_MATERIALIZED_CATALOGUE")
            self.assertEqual(entry["showroom"]["zone"], "LegacyReview")
            self.assertEqual(entry["proof"]["strongest_state"], "TINY3D_VERIFIED")
            self.assertFalse(entry["proof"]["p3_runtime_proven"])
            self.assertEqual(entry["proof"]["durable_visual"]["state"], "NOT_DECLARED")
            self.assertEqual(entry["proof"]["durable_motion_sequence"]["state"], "NOT_DECLARED")
            self.assertEqual(entry["proof"]["independent_review_state"], "NOT_RECORDED")
            self.assertEqual(entry["reopen"]["inspect_command"][2], "show")
            self.assertEqual(before, (cache_path.read_bytes(), showroom_path.read_bytes()))

    def test_search_alias_matches_materialized_catalogue_record(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            asset_id, _, _, _ = self._fixture(root)
            result = project_current("basalt ferns", root)
            self.assertEqual(result["count"], 1)
            self.assertEqual(result["entries"][0]["asset_id"], asset_id)

    def test_signature_mismatch_hides_cached_proof_as_current_truth(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _, mesh, _, _ = self._fixture(root)
            mesh.write_bytes(b"changed-after-cache")
            result = project_current("android", root)
            entry = result["entries"][0]
            self.assertEqual(entry["cache_freshness"]["state"], "STALE_SIGNATURE_MISMATCH")
            self.assertEqual(entry["proof"]["current_state"], "UNKNOWN_STALE_OR_UNVERIFIED_CACHE")
            self.assertNotIn("strongest_state", entry["proof"])

    def test_no_match_returns_bounded_empty_projection(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self._fixture(root)
            result = project_current("not-present", root)
            self.assertEqual(result["count"], 0)
            self.assertEqual(result["entries"], [])
            self.assertFalse(result["truncated"])

    def test_showroom_link_is_materialized_evidence_not_live_freshness_claim(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self._fixture(root)
            result = project_current("android", root)
            showroom = result["entries"][0]["showroom"]
            self.assertEqual(showroom["freshness_semantics"], "MATERIALIZED_SOURCE_ONLY_NO_LIVE_FRESHNESS_ASSERTION")
            self.assertIn("MATERIALIZED_SOURCE_ONLY", result["sources"]["showroom_catalogue"]["freshness_semantics"])


if __name__ == "__main__":
    unittest.main()
