"""Domain model for Corpora.

Nine nouns. If a thing being built is not one of these or a function between them,
it is not v1. See docs/architecture.md for the reasoning behind each field.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# Corpus
# --------------------------------------------------------------------------- #


class Document(BaseModel):
    """A single source document inside a snapshot."""

    doc_key: str
    """Where this document currently lives: the normalized path relative to the corpus root.

    A LOCATOR, not identity. Identity is `Anchor.span_hash`. `doc_key` tells resolution
    which document to search first; when it misses, the cascade searches the rest of the
    snapshot and finds the span anyway. That is why a renamed file resolves to
    VALID_RELOCATED rather than DESTROYED, with no rename detection and no id mapping.
    Never treat a `doc_key` match as evidence that the evidence is intact. See ADR-0010.
    """

    source_path: str
    """Where it was found at capture time. Diagnostic only, never identity."""

    content_hash: str
    """SHA-256 of normalized text. Two documents with the same hash are the same document."""

    normalized_text: str

    headings: list[HeadingSpan] = Field(default_factory=list)
    """Heading structure extracted at load time, used for heading_path resolution."""

    loader: str
    """Which loader produced normalized_text: markdown | text | xlsx | pdf."""

    loader_version: str
    """Pinned version of the extraction library. PDF text extraction is non-deterministic
    across versions; anchors are only valid within a loader version."""

    metadata: dict[str, Any] = Field(default_factory=dict)


class HeadingSpan(BaseModel):
    """One heading and the character range of the body beneath it."""

    path: list[str]
    """Full ancestry, e.g. ["3 Fire Protection", "3.2 Dampers", "3.2.1 Rated Assemblies"]."""

    level: int
    start: int
    end: int


class Snapshot(BaseModel):
    """Immutable capture of an entire corpus at one revision."""

    snapshot_id: str
    """Content hash of the whole snapshot, or a Git commit SHA when the source is a repo."""

    captured_at: datetime
    source: str
    """URI or path of the corpus root."""

    documents: dict[str, Document] = Field(default_factory=dict)
    """Keyed by doc_key."""

    normalizer_version: str
    """Stamped from corpus.normalize.NORMALIZER_VERSION. Changing the normalizer
    invalidates every anchor captured under the old version."""

    loader_versions: dict[str, str] = Field(default_factory=dict)
    """loader name -> pinned library version, e.g. {"pdf": "pymupdf==1.24.10"}."""


# --------------------------------------------------------------------------- #
# Anchors — the core
# --------------------------------------------------------------------------- #


class Resolution(str, Enum):
    """What re-resolving an anchor against a later snapshot OBSERVED.

    Observation only. A `Resolution` says what was found. It never says what to do about
    it — repair, review, and retirement are decided by `anchors.policy`, above the
    cascade. The split matters because the three actions are not equally reversible: a
    repair is silent and undoable, a review costs someone ten minutes, and a retirement
    removes a test from a customer's coverage permanently and tells nobody. Only the
    first two may be inferred from a single observation. See ADR-0008.
    """

    VALID = "valid"
    """Span found exactly once, where the anchor said, with its surroundings unchanged."""

    VALID_REPAIRED = "valid_repaired"
    """Span found exactly once under the same heading in the same document, but its
    position or its surroundings changed, so the anchor was updated to match."""

    VALID_RELOCATED = "valid_relocated"
    """Span found exactly once under a different heading, or in a different document.
    The anchor was updated; the address change is worth a low-priority note."""

    STALE = "stale"
    """Heading resolves, span does not. THE ANSWER TEXT CHANGED. The test still runs and
    its expected answer is now wrong. This is the case the product exists to catch."""

    AMBIGUOUS = "ambiguous"
    """Span found in two or more locations. Cannot decide which one the test meant."""

    DESTROYED = "destroyed"
    """Span, heading, and context all failed to resolve.

    This is a statement about one snapshot, not a verdict on the test. Sections get
    emptied in one commit and refilled in the next; a document gets moved out of the
    corpus and moved back. Retiring a test on one observation would delete coverage for
    a transient state and tell nobody. Retirement requires a policy decision over
    history — see `anchors.policy` and ADR-0008.
    """


class Action(str, Enum):
    """What to DO about a `Resolution`.

    Produced by `anchors.policy`, never by `resolve()`. Kept separate from `Resolution`
    so that a change in policy — how patient we are before proposing retirement, say —
    cannot be mistaken for a change in what the cascade observed.
    """

    NONE = "none"
    """Nothing to do. Nothing changed around this anchor."""

    REPAIR = "repair"
    """Update the anchor to its new position or context. Silent; costs no review time."""

    REPAIR_AND_NOTE = "repair_and_note"
    """Update the anchor and surface a low-priority note that its address changed."""

    REVIEW = "review"
    """A human must judge this before the next run is a valid measurement."""

    WATCH = "watch"
    """Evidence was not visible in this snapshot. Record the observation and carry the
    test forward UNCHANGED. Repeated observations may eventually make it a retirement
    candidate; one never does."""

    RETIRE = "retire"
    """Remove the test from the benchmark. Destructive, unrecoverable, and invisible to
    the customer once done. Never derived from a single `Resolution` — it requires a
    retirement policy evaluated over history plus explicit human confirmation.
    See `anchors.policy.may_retire`."""


SPAN_FOUND: frozenset[Resolution] = frozenset(
    {Resolution.VALID, Resolution.VALID_REPAIRED, Resolution.VALID_RELOCATED}
)
"""Observation: the anchored text still exists and was located exactly once."""

NEEDS_REVIEW: frozenset[Resolution] = frozenset(
    {Resolution.STALE, Resolution.AMBIGUOUS}
)
"""Resolutions that block a valid measurement until a human judges them.

DESTROYED is deliberately absent. It is not a review item and it is not a retirement:
it goes on a watchlist and accrues history. See `anchors.policy`.
"""


class Anchor(BaseModel):
    """A re-resolvable pointer to evidence inside a document.

    Redundant by design. Any single signal can break; the cascade uses whichever
    survive, and *which ones broke* is the diagnostic output.

    Never identify evidence positionally. A positional chunk index shifts whenever a
    paragraph is inserted above it, which silently repoints every downstream test.
    """

    doc_key: str
    """The document this span was captured from. A locator — resolution searches here
    first and falls through to the rest of the snapshot. See ADR-0010."""

    heading_path: list[str]
    span_hash: str
    """SHA-256 of the normalized answer text. Primary identity."""

    context_hash: str
    """SHA-256 of a normalized window around the span. Fuzzy-repair signal only."""

    char_range: tuple[int, int]
    """Position at capture time. Weakest signal — used to disambiguate and to repair,
    never as identity."""

    snapshot_id: str
    span_text: str
    """The normalized answer text itself. Kept so a human reviewing a STALE result can
    see what the answer used to say without re-fetching the old snapshot."""


class ResolutionResult(BaseModel):
    """What happened when one anchor was resolved against a later snapshot."""

    anchor: Anchor
    resolution: Resolution
    new_char_range: tuple[int, int] | None = None
    new_heading_path: list[str] | None = None
    candidate_spans: list[str] = Field(default_factory=list)
    """For STALE: what the text under the heading says now. For AMBIGUOUS: every match."""

    note: str | None = None


# --------------------------------------------------------------------------- #
# Questions
# --------------------------------------------------------------------------- #


class TriageBucket(str, Enum):
    """Deterministic classification of a generated candidate.

    Five primary, two exploratory, four reject. Only PRIMARY buckets are eligible for
    promotion into a frozen benchmark.
    """

    # primary
    FACTUAL_LOOKUP = "factual_lookup"
    IDENTIFIER_LOOKUP = "identifier_lookup"
    TABLE_LOOKUP = "table_lookup"
    CROSS_REFERENCE = "cross_reference"
    APPLICABILITY_SCOPED = "applicability_scoped"

    # exploratory
    MULTI_HOP = "multi_hop"
    AMBIGUOUS_INTENT = "ambiguous_intent"

    # reject
    REJECT_UNGROUNDED = "reject_ungrounded"
    """Quoted answer span not found byte-identical in the source."""
    REJECT_TOKEN_MISMATCH = "reject_token_mismatch"
    """A technical identifier in the question does not appear verbatim in the span."""
    REJECT_DUPLICATE = "reject_duplicate"
    REJECT_UNANSWERABLE = "reject_unanswerable"


PRIMARY_BUCKETS: frozenset[TriageBucket] = frozenset(
    {
        TriageBucket.FACTUAL_LOOKUP,
        TriageBucket.IDENTIFIER_LOOKUP,
        TriageBucket.TABLE_LOOKUP,
        TriageBucket.CROSS_REFERENCE,
        TriageBucket.APPLICABILITY_SCOPED,
    }
)


class FailureMode(str, Enum):
    """What a test is designed to probe. Turns a score into a diagnosis.

    "Your retrieval is 91%" is a number. "Your retrieval is 58% on applicability-scoped
    questions" is an instruction.
    """

    PLAIN_LOOKUP = "plain_lookup"
    ACRONYM_COLLISION = "acronym_collision"
    TECHNICAL_IDENTIFIER = "technical_identifier"
    VERSION_APPLICABILITY = "version_applicability"
    NEAR_DUPLICATE_SECTION = "near_duplicate_section"
    CROSS_DOCUMENT_REFERENCE = "cross_document_reference"
    TABLE_RESIDENT_FACT = "table_resident_fact"


class Candidate(BaseModel):
    """A generated question that has not yet been reviewed."""

    candidate_id: str
    question: str
    anchor: Anchor
    quoted_span: str
    """What the generator claimed the answer text is. Must match the source byte-identically
    or the candidate is REJECT_UNGROUNDED."""

    bucket: TriageBucket
    failure_mode: FailureMode
    applicability: dict[str, str] = Field(default_factory=dict)
    source: Literal["documents", "query_log"] = "documents"
    generator: str
    """Model identifier, for provenance. Never used in grading."""

    triage_notes: list[str] = Field(default_factory=list)


class ReviewState(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class TestCase(BaseModel):
    """A promoted candidate, frozen into a benchmark."""

    test_id: str
    question: str
    anchor: Anchor
    expected_doc_key: str
    bucket: TriageBucket
    failure_mode: FailureMode

    applicability: dict[str, str] = Field(default_factory=dict)
    """A test is not "question -> expected document". It is "question, within this filter
    context, -> expected document". Jurisdiction, product line, customer, region."""

    review_state: ReviewState = ReviewState.ACCEPTED
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_seconds: float | None = None
    """Expert-minutes per accepted test is the metric we sell on. Measure it from day one;
    the prior project never did and could not answer the question afterward."""


class BenchmarkKind(str, Enum):
    FROZEN = "frozen"
    """Curated, human-accepted, small. CI gates on this."""
    HELDOUT = "heldout"
    """Synthetic, uncurated, larger. Detects overfitting to the frozen set."""


class Benchmark(BaseModel):
    benchmark_id: str
    kind: BenchmarkKind
    snapshot_id: str
    tests: list[TestCase]
    dataset_hash: str
    """SHA-256 over the ordered test set. Half of the same-contract comparison gate."""

    created_at: datetime
    frozen: bool = True


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #


class Hit(BaseModel):
    """One result returned by the system under test."""

    doc_key: str
    text: str
    score: float | None = None
    native_id: str | None = None
    trace: dict[str, Any] | None = None
    """Optional per-stage diagnostics from the target, e.g. candidate counts by pipeline
    stage. On the prior system a trace reading prefilter=0, keyword=0, embedding=0, rrf=0
    is what localized a catastrophic failure to the prefilter boundary rather than to
    ranking. If a target can expose this, capture it."""


class TransportErrorKind(str, Enum):
    """A transport failure is NOT a retrieval miss. Counting a timeout as a miss makes
    recall lie."""

    TIMEOUT = "timeout"
    TLS = "tls"
    PROXY = "proxy"
    DNS = "dns"
    AUTH = "auth"
    SERVER_ERROR = "server_error"
    UNKNOWN = "unknown"


class TransportError(BaseModel):
    test_id: str
    kind: TransportErrorKind
    detail: str


class TestOutcome(BaseModel):
    test_id: str
    hits: list[Hit]
    latency_ms: float
    empty: bool
    """No hits returned at all. Tracked separately from "wrong hits" — on the prior system
    29 of 59 empty results were the finding that exposed the whole failure."""


class RunConfig(BaseModel):
    """Immutable. Hashed and bound to every report."""

    top_k: int = 10
    timeout_s: float = 30.0
    max_retries: int = 3
    filters: dict[str, str] = Field(default_factory=dict)
    config_hash: str = ""


class Run(BaseModel):
    run_id: str
    benchmark_id: str
    dataset_hash: str
    config: RunConfig
    target_id: str
    """Stable identity of the system under test. Part of the comparison gate."""

    identity: str
    """Who the run executed as. Results are only interpretable relative to the access scope
    of this identity — a run by a user who cannot see half the corpus is not a quality
    measurement."""

    started_at: datetime
    finished_at: datetime | None = None
    outcomes: list[TestOutcome] = Field(default_factory=list)
    transport_errors: list[TransportError] = Field(default_factory=list)
    integrity_ok: bool = False
    """False if any anchor in the benchmark failed to resolve against the current snapshot.
    A run over a benchmark with unresolved anchors is not a valid measurement."""


class Metrics(BaseModel):
    context_precision: float
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    recall_at_10: float
    mrr: float
    map: float
    ndcg: float
    wrong_top_1_rate: float
    median_latency_ms: float
    p95_latency_ms: float
    empty_count: int
    error_count: int
    estimated_cost_usd: float | None = None
    """Known gap in the prior work. An eval that scores quality but not cost cannot
    adjudicate a change that trades one for the other."""


class Report(BaseModel):
    report_id: str
    run: Run
    metrics: Metrics
    metrics_by_failure_mode: dict[FailureMode, Metrics] = Field(default_factory=dict)
    """The diagnostic output. "91% overall, 58% on applicability-scoped" is the deliverable."""

    per_test: dict[str, bool] = Field(default_factory=dict)


class Comparison(BaseModel):
    """Result of comparing two reports. Only produced if the same-contract gate passes."""

    baseline_report_id: str
    candidate_report_id: str
    contract_ok: bool
    contract_violations: list[str] = Field(default_factory=list)
    aggregate_deltas: dict[str, float] = Field(default_factory=dict)
    regressed_tests: list[str] = Field(default_factory=list)
    """Per-query regressions. The decisive finding on the prior system was "three
    previously-passing queries regressed" — invisible in the aggregate."""

    improved_tests: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Diff
# --------------------------------------------------------------------------- #


class Diff(BaseModel):
    """What changed between two snapshots, and which tests it affects."""

    from_snapshot_id: str
    to_snapshot_id: str
    computed_at: datetime
    """When this diff was computed.

    Required, not defaulted: `policy.should_propose_retirement` needs an ordered
    `(datetime, Resolution)` history per anchor, and a default would silently stamp the
    wrong time on a diff replayed from stored snapshots. Nothing accumulates this yet —
    the history store belongs with `run/` and SQLite. This field is the seam so the data
    exists when that gets built. See ADR-0008.
    """

    added_docs: list[str] = Field(default_factory=list)
    removed_docs: list[str] = Field(default_factory=list)
    changed_docs: list[str] = Field(default_factory=list)
    resolutions: list[ResolutionResult] = Field(default_factory=list)

    @property
    def needs_review(self) -> list[ResolutionResult]:
        """Anchors a human must judge before the next run is a valid measurement."""
        return [r for r in self.resolutions if r.resolution in NEEDS_REVIEW]

    @property
    def repaired(self) -> list[ResolutionResult]:
        """Anchors that were found and updated without costing anyone review time."""
        return [
            r
            for r in self.resolutions
            if r.resolution in SPAN_FOUND and r.resolution is not Resolution.VALID
        ]

    @property
    def unresolved(self) -> list[ResolutionResult]:
        """Anchors whose evidence was not visible in this snapshot.

        NOT a retirement list, and deliberately not named like one. A single diff cannot
        justify retiring a test — the section may be refilled in the next commit. These
        go on a watchlist; `anchors.policy` decides over history whether any of them is
        a retirement candidate, and a human confirms. See ADR-0008.
        """
        return [r for r in self.resolutions if r.resolution is Resolution.DESTROYED]


Document.model_rebuild()
