"""Refresh owned Wikimasters cards while retaining locally curated wanted cards."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
COLLECTION_URLS = {
    "bike": "https://www.wiki-masters.com/api/my-collection?sort=rarity&tag_id=1f306648-72a1-44a7-82d2-e5a6b37fee65&page=0&stats=0",
    "cac40": "https://www.wiki-masters.com/api/my-collection?sort=name&tag_id=ed71f8ea-7e11-45d5-b92b-3abbb64d0048&page=0&stats=0",
    "geek": "https://www.wiki-masters.com/api/my-collection?sort=rarity&tag_id=a8b6f623-5290-4fed-b0d5-2658f10b5c60&page=0&stats=0",
}
REQUEST_TIMEOUT_SECONDS = 30
MAX_PAGES = 1000


def load_cookie(root: Path = ROOT) -> str:
    """Read the session cookie from the process environment or a local .env file."""
    cookie = os.environ.get("WIKIMASTERS_COOKIE", "").strip()
    env_file = root / ".env"

    if not cookie and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            key, separator, value = stripped.partition("=")
            if separator and key.strip() == "WIKIMASTERS_COOKIE":
                cookie = value.strip()
                if len(cookie) >= 2 and cookie[0] == cookie[-1] and cookie[0] in "'\"":
                    cookie = cookie[1:-1]
                break

    cookie = re.sub(r"^Cookie:\s*", "", cookie, flags=re.IGNORECASE).strip()
    if not cookie:
        raise RuntimeError(
            "Cookie manquant. Renseigne WIKIMASTERS_COOKIE dans le fichier .env local."
        )
    return cookie


def url_for_page(endpoint: str, page: int) -> str:
    parts = urlsplit(endpoint)
    query = parse_qsl(parts.query, keep_blank_values=True)
    updated_query: list[tuple[str, str]] = []
    page_replaced = False

    for key, value in query:
        if key == "page":
            updated_query.append((key, str(page)))
            page_replaced = True
        else:
            updated_query.append((key, value))

    if not page_replaced:
        updated_query.append(("page", str(page)))

    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(updated_query), parts.fragment))


def fetch_owned_collection(
    endpoint: str,
    cookie: str,
    opener: Callable[..., Any] = urlopen,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Fetch pages until the API returns an empty page; fail on malformed responses."""
    all_entries: list[dict[str, Any]] = []
    seen_page_signatures: set[tuple[str, ...]] = set()
    first_payload: dict[str, Any] | None = None

    for page in range(MAX_PAGES):
        request = Request(
            url_for_page(endpoint, page),
            headers={
                "Cookie": cookie,
                "Accept": "application/json",
                "User-Agent": "WikimasterPortfolioUpdater/1.0",
            },
        )
        try:
            with opener(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Échec de la requête de collection (page {page}).") from error

        if not isinstance(payload, dict) or not isinstance(payload.get("collection"), list):
            raise RuntimeError(f"Réponse API invalide pour la page {page}: collection absente.")

        if first_payload is None:
            first_payload = {key: value for key, value in payload.items() if key != "collection"}

        page_entries = payload["collection"]
        if not page_entries:
            break

        for entry in page_entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("card"), dict):
                raise RuntimeError(f"Entrée de carte invalide dans la page {page}.")

        signature = tuple(sorted(_card_id(entry) or _wiki_key(entry) for entry in page_entries))
        if signature in seen_page_signatures:
            raise RuntimeError(f"L'API a répété la page {page}; aucune donnée n'a été écrite.")
        seen_page_signatures.add(signature)

        all_entries.extend(page_entries)
    else:
        raise RuntimeError(f"Limite de {MAX_PAGES} pages atteinte; aucune donnée n'a été écrite.")

    if first_payload is None:
        raise RuntimeError("L'API n'a retourné aucune réponse exploitable.")
    return first_payload, all_entries


def _card_id(entry: dict[str, Any]) -> str:
    card = entry.get("card")
    if not isinstance(card, dict):
        return ""
    value = card.get("id") or entry.get("card_id")
    return str(value) if value else ""


def _normalize_title(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    without_marks = "".join(character for character in decomposed if not unicodedata.combining(character))
    return "".join(character for character in without_marks if character.isalnum())


def _wiki_key(entry: dict[str, Any]) -> str:
    card = entry.get("card")
    if not isinstance(card, dict):
        return ""

    title = card.get("wikipedia_title")
    if isinstance(title, str) and title.strip():
        return _normalize_title(title.strip())

    wiki_url = card.get("wikipedia_url")
    if isinstance(wiki_url, str) and wiki_url.strip():
        path_title = unquote(urlsplit(wiki_url).path.rsplit("/", 1)[-1]).replace("_", " ")
        return _normalize_title(path_title)
    return ""


def _identity_keys(entry: dict[str, Any]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    card_id = _card_id(entry)
    wiki_key = _wiki_key(entry)
    if card_id:
        keys.add(("id", card_id))
    if wiki_key:
        keys.add(("wiki", wiki_key))
    return keys


def _merge_tags(api_entry: dict[str, Any], local_entries: list[dict[str, Any]]) -> None:
    api_tags = api_entry.get("tags")
    if not isinstance(api_tags, list):
        api_tags = []

    merged_tags: list[Any] = []
    seen: set[str] = set()
    local_tags = [
        tag
        for entry in local_entries
        for tag in (entry.get("tags") if isinstance(entry.get("tags"), list) else [])
    ]
    for tag in [*api_tags, *local_tags]:
        if isinstance(tag, str):
            name = tag
        elif isinstance(tag, dict) and isinstance(tag.get("name"), str):
            name = tag["name"]
        else:
            continue
        key = _normalize_title(name)
        if key and key not in seen:
            merged_tags.append(tag)
            seen.add(key)
    api_entry["tags"] = merged_tags


def merge_collection(
    existing_document: dict[str, Any],
    api_metadata: dict[str, Any],
    api_entries: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, int]]:
    """Refresh API-owned entries and retain every local entry missing from the API."""
    existing_entries = existing_document.get("collection")
    if not isinstance(existing_entries, list):
        raise ValueError("Le JSON local doit contenir une liste « collection ».")

    normalized_api: list[dict[str, Any]] = []
    api_keys: set[tuple[str, str]] = set()
    for raw_entry in api_entries:
        if not isinstance(raw_entry, dict) or not isinstance(raw_entry.get("card"), dict):
            raise ValueError("Une entrée API est invalide; aucune donnée n'a été écrite.")
        api_entry = copy.deepcopy(raw_entry)
        api_entry["owned"] = True
        keys = _identity_keys(api_entry)
        if not keys:
            raise ValueError("Une carte API n'a ni identifiant ni titre Wikipedia exploitable.")
        if keys & api_keys:
            continue

        matching_local = [
            entry
            for entry in existing_entries
            if isinstance(entry, dict)
            and entry.get("owned") is False
            and bool(keys & _identity_keys(entry))
        ]
        _merge_tags(api_entry, matching_local)
        normalized_api.append(api_entry)
        api_keys.update(keys)

    retained_entries: list[dict[str, Any]] = []
    promoted = 0
    preserved_wanted = 0
    preserved_missing_owned = 0
    for entry in existing_entries:
        if not isinstance(entry, dict):
            raise ValueError("Une entrée du JSON local est invalide; aucune donnée n'a été écrite.")
        keys = _identity_keys(entry)
        if keys & api_keys:
            if entry.get("owned") is False:
                promoted += 1
            continue

        retained_entries.append(copy.deepcopy(entry))
        if entry.get("owned") is False:
            preserved_wanted += 1
        else:
            preserved_missing_owned += 1

    result = copy.deepcopy(existing_document)
    result.update({key: copy.deepcopy(value) for key, value in api_metadata.items() if key != "collection"})
    result["collection"] = [*normalized_api, *retained_entries]
    stats = {
        "fetched": len(normalized_api),
        "promoted": promoted,
        "preserved_wanted": preserved_wanted,
        "preserved_missing_owned": preserved_missing_owned,
    }
    return result, stats


def _stage_json(path: Path, document: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
    ) as temporary_file:
        json.dump(document, temporary_file, ensure_ascii=False, indent=2)
        temporary_file.write("\n")
        return Path(temporary_file.name)


def update_collections(cookie: str, root: Path = ROOT, dry_run: bool = False) -> dict[str, dict[str, int]]:
    """Fetch every configured API collection before staging or replacing local files."""
    pending: list[tuple[Path, dict[str, Any], dict[str, int]]] = []

    for name, endpoint in COLLECTION_URLS.items():
        path = root / "data" / f"{name}_collection.json"
        if not path.exists():
            raise FileNotFoundError(f"Fichier de collection absent: {path}")
        existing_document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(existing_document, dict):
            raise ValueError(f"Le JSON de {name} doit être un objet.")

        api_metadata, api_entries = fetch_owned_collection(endpoint, cookie)
        merged, stats = merge_collection(existing_document, api_metadata, api_entries)
        pending.append((path, merged, stats))

    if dry_run:
        return {path.stem.removesuffix("_collection"): stats for path, _, stats in pending}

    staged: list[tuple[Path, Path]] = []
    try:
        for path, document, _ in pending:
            staged.append((_stage_json(path, document), path))
        for temporary_path, target_path in staged:
            temporary_path.replace(target_path)
    finally:
        for temporary_path, _ in staged:
            temporary_path.unlink(missing_ok=True)

    return {path.stem.removesuffix("_collection"): stats for path, _, stats in pending}


def main() -> int:
    parser = argparse.ArgumentParser(description="Met à jour les collections Wikimasters sans supprimer les cartes voulues.")
    parser.add_argument("--dry-run", action="store_true", help="récupère et simule le merge sans écrire les JSON")
    args = parser.parse_args()

    try:
        results = update_collections(load_cookie(), dry_run=args.dry_run)
    except (FileNotFoundError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"Mise à jour annulée : {error}")
        return 1

    action = "Simulation" if args.dry_run else "Mise à jour"
    for name, stats in results.items():
        print(
            f"{action} {name}: {stats['fetched']} cartes API, "
            f"{stats['promoted']} carte(s) voulue(s) passée(s) en possédée(s), "
            f"{stats['preserved_wanted']} carte(s) voulue(s) conservée(s)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())