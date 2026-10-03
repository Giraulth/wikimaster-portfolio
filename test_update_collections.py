import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from update_collections import fetch_owned_collection, load_cookie, merge_collection, update_collections, url_for_page


def make_entry(card_id: str, title: str, *, owned: bool | None = None, tags: list | None = None) -> dict:
    entry = {
        "id": f"entry-{card_id}",
        "card": {
            "id": card_id,
            "rarity": "UR",
            "image_url": None,
            "hide_image": False,
            "wikipedia_url": f"https://fr.wikipedia.org/wiki/{title.replace(' ', '_')}",
            "wikipedia_title": title,
        },
        "tags": tags or [],
        "card_id": card_id,
    }
    if owned is not None:
        entry["owned"] = owned
    return entry


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.body = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        self.body.close()

    def read(self) -> bytes:
        return self.body.read()


class UpdateCollectionsTests(unittest.TestCase):
    def test_url_for_page_replaces_only_the_page_query_parameter(self) -> None:
        result = url_for_page("https://example.com/api?sort=name&page=0&stats=0", 3)

        self.assertEqual(result, "https://example.com/api?sort=name&page=3&stats=0")

    def test_load_cookie_reads_local_env_and_strips_cookie_header_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / ".env").write_text('WIKIMASTERS_COOKIE="Cookie: session=local-secret"\n', encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(load_cookie(root), "session=local-secret")

    def test_fetch_owned_collection_sends_cookie_and_reads_until_empty_page(self) -> None:
        responses = iter([
            FakeResponse({"collection": [make_entry("one", "Airbus")], "total": None}),
            FakeResponse({"collection": []}),
        ])
        requested_pages: list[str] = []

        def opener(request, timeout):
            self.assertEqual(request.get_header("Cookie"), "session=test-cookie")
            self.assertEqual(timeout, 30)
            requested_pages.append(request.full_url)
            return next(responses)

        metadata, entries = fetch_owned_collection(
            "https://example.com/api?sort=name&page=0&stats=0",
            "session=test-cookie",
            opener=opener,
        )

        self.assertEqual(metadata, {"total": None})
        self.assertEqual([entry["card"]["id"] for entry in entries], ["one"])
        self.assertIn("page=0", requested_pages[0])
        self.assertIn("page=1", requested_pages[1])

    def test_merge_refreshes_owned_promotes_matching_wanted_and_preserves_other_wanted(self) -> None:
        wanted_airbus = make_entry("wanted-airbus", "Airbus", owned=False, tags=[{"name": "cac40"}])
        wanted_legrand = make_entry("wanted-legrand", "Legrand", owned=False, tags=[{"name": "cac40"}])
        missing_owned = make_entry("old-owned", "Old owned card")
        existing = {"collection": [wanted_airbus, wanted_legrand, missing_owned], "custom": "kept"}
        api_airbus = make_entry("api-airbus", "Airbus", tags=[{"name": "aircraft"}])
        api_new_card = make_entry("api-new", "New card")

        merged, stats = merge_collection(existing, {"total": 2}, [api_airbus, api_new_card])

        entries = merged["collection"]
        self.assertEqual([entry["card"]["id"] for entry in entries], ["api-airbus", "api-new", "wanted-legrand", "old-owned"])
        self.assertTrue(entries[0]["owned"])
        self.assertEqual({tag["name"] for tag in entries[0]["tags"]}, {"aircraft", "cac40"})
        self.assertFalse(entries[2]["owned"])
        self.assertEqual(merged["custom"], "kept")
        self.assertEqual(merged["total"], 2)
        self.assertEqual(stats, {
            "fetched": 2,
            "promoted": 1,
            "preserved_wanted": 1,
            "preserved_missing_owned": 1,
        })

    def test_merge_matches_wanted_card_by_normalized_wikipedia_title(self) -> None:
        local_card = make_entry("wanted-loreal", "L'Oréal", owned=False)
        api_card = make_entry("api-loreal", "L'Oréal")

        merged, stats = merge_collection({"collection": [local_card]}, {}, [api_card])

        self.assertEqual(len(merged["collection"]), 1)
        self.assertEqual(merged["collection"][0]["card"]["id"], "api-loreal")
        self.assertTrue(merged["collection"][0]["owned"])
        self.assertEqual(stats["promoted"], 1)

    def test_failed_collection_request_does_not_write_any_json_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            data_directory = root / "data"
            data_directory.mkdir()
            original_contents = {}
            for name in ("bike", "cac40", "geek"):
                path = data_directory / f"{name}_collection.json"
                path.write_text(json.dumps({"collection": [], "marker": name}), encoding="utf-8")
                original_contents[path] = path.read_bytes()

            with patch(
                "update_collections.fetch_owned_collection",
                side_effect=[({"total": 0}, []), RuntimeError("simulated HTTP failure")],
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated HTTP failure"):
                    update_collections("session=test-cookie", root)

            for path, original_content in original_contents.items():
                self.assertEqual(path.read_bytes(), original_content)


if __name__ == "__main__":
    unittest.main()