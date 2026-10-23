"""Approved-source retrieval adapters for the non-runtime review workspace."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Protocol
from urllib.parse import urlencode
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from html.parser import HTMLParser
import re
import unicodedata

DAILYMED_API = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
MAX_SOURCE_BYTES = 12 * 1024 * 1024


class SourceRetrievalError(Exception):
    pass


class Transport(Protocol):
    def get(self, url: str) -> tuple[bytes, dict[str, str]]: ...


class UrlLibTransport:
    def get(self, url: str) -> tuple[bytes, dict[str, str]]:
        if not url.startswith(DAILYMED_API + "/"):
            raise SourceRetrievalError("Unapproved source URL")
        request = Request(url, headers={"User-Agent": "RiskSenseEvidenceReview/1.0"})
        try:
            with urlopen(request, timeout=20) as response:  # nosec B310: fixed HTTPS host checked above
                data = response.read(MAX_SOURCE_BYTES + 1)
                if len(data) > MAX_SOURCE_BYTES:
                    raise SourceRetrievalError("Source exceeds size limit")
                return data, {key.lower(): value for key, value in response.headers.items()}
        except SourceRetrievalError:
            raise
        except Exception:
            raise SourceRetrievalError("DailyMed retrieval failed") from None


@dataclass(frozen=True)
class SourceSnapshot:
    source_family: str
    source_identifier: str
    source_url: str
    source_revision_date: str | None
    content: bytes
    content_hash: str


class DailyMedAdapter:
    def __init__(self, transport: Transport | None = None):
        self.transport = transport or UrlLibTransport()

    def locate(self, canonical_name: str) -> tuple[dict, ...]:
        query = urlencode({"drug_name": canonical_name, "pagesize": 20, "page": 1})
        data, _ = self.transport.get(f"{DAILYMED_API}/spls.json?{query}")
        try:
            payload = json.loads(data)
            candidates = payload.get("data", payload.get("spls", []))
            result = []
            for item in candidates:
                set_id = item.get("setid") or item.get("set_id")
                title = item.get("title") or item.get("drug_name") or ""
                if set_id:
                    result.append({"set_id": str(set_id), "title": str(title)})
            return tuple(result)
        except Exception:
            raise SourceRetrievalError("DailyMed search response was invalid") from None

    def locate_all(self, canonical_name: str, *, max_pages: int = 30) -> tuple[dict, ...]:
        """Read every current search page; a truncated list cannot prove uniqueness."""
        result: dict[str, dict] = {}
        for page in range(1, max_pages + 1):
            query = urlencode({"drug_name": canonical_name, "pagesize": 100, "page": page})
            data, _ = self.transport.get(f"{DAILYMED_API}/spls.json?{query}")
            try:
                payload = json.loads(data)
                metadata = payload["metadata"]
                total_pages = int(metadata["total_pages"])
                if total_pages < 1 or total_pages > max_pages or page > total_pages:
                    raise ValueError("invalid pagination")
                for item in payload["data"]:
                    set_id = str(item["setid"])
                    if not re.fullmatch(r"[a-fA-F0-9-]{36}", set_id):
                        raise ValueError("invalid SET ID")
                    result[set_id] = {
                        "set_id": set_id, "title": str(item.get("title") or ""),
                        "spl_version": str(item.get("spl_version") or ""),
                        "published_date": str(item.get("published_date") or ""),
                    }
                if page == total_pages:
                    return tuple(result.values())
            except (KeyError, TypeError, ValueError):
                raise SourceRetrievalError("DailyMed paginated search response was invalid") from None
        raise SourceRetrievalError("DailyMed search exceeded page safety limit")

    def retrieve(self, set_id: str) -> SourceSnapshot:
        if not set_id or any(character not in "0123456789abcdefABCDEF-" for character in set_id):
            raise SourceRetrievalError("Invalid DailyMed SET ID")
        url = f"{DAILYMED_API}/spls/{set_id}.xml"
        content, headers = self.transport.get(url)
        if not content.lstrip().startswith(b"<?xml"):
            raise SourceRetrievalError("DailyMed SPL was not XML")
        return SourceSnapshot(
            source_family="DAILYMED", source_identifier=set_id, source_url=url,
            source_revision_date=headers.get("x-dailymed-label-last-updated"),
            content=content, content_hash=sha256(content).hexdigest(),
        )


MOTHERTOBABY_INDEX = "https://mothertobaby.org/fact-sheets/"


class MotherToBabyTransport:
    def get(self, url: str) -> tuple[bytes, dict[str, str]]:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != "mothertobaby.org":
            raise SourceRetrievalError("Unapproved source URL")
        try:
            with urlopen(Request(url, headers={"User-Agent": "RiskSenseEvidenceReview/1.0"}), timeout=20) as response:  # nosec B310
                data = response.read(MAX_SOURCE_BYTES + 1)
                if len(data) > MAX_SOURCE_BYTES:
                    raise SourceRetrievalError("Source exceeds size limit")
                return data, {key.lower(): value for key, value in response.headers.items()}
        except SourceRetrievalError:
            raise
        except Exception:
            raise SourceRetrievalError("MotherToBaby retrieval failed") from None


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.current = None
        self.text = []
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.current = dict(attrs).get("href")
            self.text = []
    def handle_data(self, data):
        if self.current is not None:
            self.text.append(data)
    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            self.links.append((self.current, " ".join(self.text)))
            self.current = None


def _normal(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKC", value).casefold()).split())


class MotherToBabyAdapter:
    def __init__(self, transport: Transport | None = None):
        self.transport = transport or MotherToBabyTransport()
        self._index = None

    def _links(self):
        if self._index is None:
            data, _ = self.transport.get(MOTHERTOBABY_INDEX)
            parser = _Links()
            parser.feed(data.decode("utf-8", errors="replace"))
            self._index = tuple({(urljoin(MOTHERTOBABY_INDEX, href), " ".join(text.split()))
                                 for href, text in parser.links if "/fact-sheets/" in href and href != MOTHERTOBABY_INDEX})
        return self._index

    def locate(self, canonical_name: str) -> tuple[dict, ...]:
        name = _normal(canonical_name)
        return tuple({"url": url, "title": title} for url, title in self._links()
                     if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", _normal(title)))

    def retrieve(self, url: str) -> SourceSnapshot:
        content, headers = self.transport.get(url)
        if b"<html" not in content[:1000].lower() and b"<!doctype html" not in content[:1000].lower():
            raise SourceRetrievalError("MotherToBaby fact sheet was not HTML")
        identifier = urlsplit(url).path.strip("/").replace("/", ":")
        return SourceSnapshot("MOTHERTOBABY", identifier, url, headers.get("last-modified"),
                              content, sha256(content).hexdigest())
