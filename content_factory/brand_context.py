from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from pydantic import Field

from content_factory.models import BrandProfile, BrandSourceKind
from schemas.base import SchemaBase


FETCH_USER_AGENT = "AIContentFactoryFetcher-1.0"


class FetchedSource(SchemaBase):
    source_id: str
    kind: str
    purpose: str
    ref: str

    fetched_at: str
    ok: bool

    sha256: Optional[str] = None
    bytes_length: Optional[int] = None

    http_status: Optional[int] = None
    robots_allowed: Optional[bool] = None

    error: Optional[str] = None


class ExtractedBrandSignals(SchemaBase):
    titles: list[str] = Field(default_factory=list)
    headings: list[str] = Field(default_factory=list)
    descriptions: list[str] = Field(default_factory=list)

    positioning_snippets: list[str] = Field(default_factory=list)
    key_terms: list[str] = Field(default_factory=list)


class BrandContextArtifact(SchemaBase):
    artifact_version: str = "1.0"
    brand_id: str
    generated_at: str
    fetch_user_agent: str

    sources: list[FetchedSource]
    signals: ExtractedBrandSignals


@dataclass(frozen=True)
class _HttpResult:
    status: int
    data: bytes


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_file_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _http_get_bytes(url: str, *, user_agent: str, timeout_seconds: float = 20.0) -> _HttpResult:
    req = Request(url, headers={"User-Agent": user_agent})
    with urlopen(req, timeout=timeout_seconds) as r:  # nosec - trusted outbound fetcher with robots gating
        status = getattr(r, "status", None) or 200
        data = r.read()
    return _HttpResult(status=status, data=data)


def _origin(url: str) -> str:
    p = urlparse(url)
    if not p.scheme or not p.netloc:
        raise ValueError(f"Invalid URL (missing scheme/host): {url}")
    return f"{p.scheme}://{p.netloc}"


def _robots_url_for(url: str) -> str:
    return urljoin(_origin(url) + "/", "robots.txt")


def _robots_allows(url: str, *, user_agent: str) -> bool:
    robots_url = _robots_url_for(url)
    res = _http_get_bytes(robots_url, user_agent=user_agent)

    # 404 -> treat as allowed.
    if res.status == 404:
        return True

    if res.status != 200:
        raise ValueError(f"robots.txt fetch failed: {robots_url} status={res.status}")

    rp = RobotFileParser()
    text = res.data.decode("utf-8", errors="replace")
    rp.parse(text.splitlines())

    # UA-specific evaluation only.
    return bool(rp.can_fetch(user_agent, url))


_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_META_DESC_RE = re.compile(
    r"<meta\s+[^>]*name=[\"']description[\"'][^>]*content=[\"'](.*?)[\"'][^>]*>",
    re.IGNORECASE | re.DOTALL,
)
_H_RE = re.compile(r"<(h1|h2)\b[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL)


def _extract_text_fields_from_html(html: str) -> ExtractedBrandSignals:
    html = _SCRIPT_STYLE_RE.sub(" ", html)

    titles = [t.strip() for t in _TITLE_RE.findall(html) if t and t.strip()]
    descriptions = [d.strip() for d in _META_DESC_RE.findall(html) if d and d.strip()]

    headings: list[str] = []
    for _, h in _H_RE.findall(html):
        h_clean = _TAG_RE.sub(" ", h)
        h_clean = " ".join(h_clean.split()).strip()
        if h_clean:
            headings.append(h_clean)

    # crude text body to derive lightweight signals
    text = _TAG_RE.sub(" ", html)
    text = " ".join(text.split())

    snippets: list[str] = []
    if headings:
        snippets.extend(headings[:5])
    if descriptions:
        snippets.extend(descriptions[:3])

    # basic token frequency for key terms
    tokens = re.findall(r"[A-Za-z][A-Za-z\-']{2,}", text.lower())
    stop = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "you",
        "your",
        "from",
        "are",
        "our",
        "but",
        "not",
        "have",
        "has",
        "was",
        "were",
        "will",
        "can",
        "how",
        "what",
        "why",
        "when",
        "who",
        "their",
        "they",
        "them",
        "into",
        "about",
        "more",
        "less",
    }
    freq: dict[str, int] = {}
    for tok in tokens:
        if tok in stop:
            continue
        freq[tok] = freq.get(tok, 0) + 1

    key_terms = [k for k, _ in sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:25]]

    return ExtractedBrandSignals(
        titles=titles[:5],
        headings=headings[:20],
        descriptions=descriptions[:5],
        positioning_snippets=snippets[:10],
        key_terms=key_terms,
    )


def _merge_signals(signals: Iterable[ExtractedBrandSignals]) -> ExtractedBrandSignals:
    merged = ExtractedBrandSignals()
    seen_terms: set[str] = set()

    for s in signals:
        for t in s.titles:
            if t not in merged.titles:
                merged.titles.append(t)
        for h in s.headings:
            if h not in merged.headings:
                merged.headings.append(h)
        for d in s.descriptions:
            if d not in merged.descriptions:
                merged.descriptions.append(d)
        for p in s.positioning_snippets:
            if p not in merged.positioning_snippets:
                merged.positioning_snippets.append(p)
        for k in s.key_terms:
            if k not in seen_terms:
                merged.key_terms.append(k)
                seen_terms.add(k)

    # cap sizes
    merged.titles = merged.titles[:10]
    merged.headings = merged.headings[:50]
    merged.descriptions = merged.descriptions[:10]
    merged.positioning_snippets = merged.positioning_snippets[:25]
    merged.key_terms = merged.key_terms[:50]
    return merged


def build_brand_context_artifact(
    *,
    brand: BrandProfile,
    repo_root: Path,
    user_agent: str = FETCH_USER_AGENT,
) -> BrandContextArtifact:
    fetched: list[FetchedSource] = []
    extracted: list[ExtractedBrandSignals] = []

    for src in brand.brand_sources.sources:
        fetched_at = _utc_now_iso()
        try:
            if src.kind == BrandSourceKind.url:
                allowed = _robots_allows(src.ref, user_agent=user_agent)
                if not allowed:
                    raise ValueError("robots.txt disallows fetching this URL")

                res = _http_get_bytes(src.ref, user_agent=user_agent)
                if res.status >= 400:
                    raise ValueError(f"HTTP error status={res.status}")

                data = res.data
                fetched.append(
                    FetchedSource(
                        source_id=src.source_id,
                        kind=src.kind.value,
                        purpose=src.purpose.value,
                        ref=src.ref,
                        fetched_at=fetched_at,
                        ok=True,
                        sha256=_sha256(data),
                        bytes_length=len(data),
                        http_status=res.status,
                        robots_allowed=True,
                    )
                )

                text = data.decode("utf-8", errors="replace")
                extracted.append(_extract_text_fields_from_html(text))

            else:
                file_path = Path(src.ref)
                if not file_path.is_absolute():
                    file_path = repo_root / file_path

                data = _read_file_bytes(file_path)
                fetched.append(
                    FetchedSource(
                        source_id=src.source_id,
                        kind=src.kind.value,
                        purpose=src.purpose.value,
                        ref=str(file_path),
                        fetched_at=fetched_at,
                        ok=True,
                        sha256=_sha256(data),
                        bytes_length=len(data),
                    )
                )

                # best-effort: treat files as UTF-8 text
                text = data.decode("utf-8", errors="replace")
                extracted.append(_extract_text_fields_from_html(text))

        except Exception as e:
            fetched.append(
                FetchedSource(
                    source_id=src.source_id,
                    kind=src.kind.value,
                    purpose=src.purpose.value,
                    ref=src.ref,
                    fetched_at=fetched_at,
                    ok=False,
                    error=str(e),
                )
            )

    failures = [s for s in fetched if not s.ok]
    if failures:
        msg = "\n".join(f"- {s.source_id}: {s.error}" for s in failures)
        raise ValueError(f"Brand source ingestion failed:\n{msg}")

    signals = _merge_signals(extracted)

    return BrandContextArtifact(
        brand_id=brand.brand_id,
        generated_at=_utc_now_iso(),
        fetch_user_agent=user_agent,
        sources=fetched,
        signals=signals,
    )


def artifact_path_for_brand(*, repo_root: Path, brand_id: str) -> Path:
    return repo_root / "content_factory" / "artifacts" / f"{brand_id}.json"


def write_brand_context_artifact(*, repo_root: Path, artifact: BrandContextArtifact) -> Path:
    out_path = artifact_path_for_brand(repo_root=repo_root, brand_id=artifact.brand_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact.to_dict(), indent=2, sort_keys=False), encoding="utf-8")
    return out_path
