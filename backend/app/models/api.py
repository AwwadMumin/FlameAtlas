"""Pydantic v2 models = single source of truth for the API contract."""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Verdict(str, Enum):
    EVIDENCE = "EVIDENCE"
    MODEL_ESTIMATE = "MODEL_ESTIMATE"
    NO_DIRECT_EVIDENCE = "NO_DIRECT_EVIDENCE"


# The frontend has no business logic: labels and colour tiers come from here.
VERDICT_META: dict[Verdict, dict[str, str]] = {
    Verdict.EVIDENCE: {"label": "Evidence", "tier": "green"},
    Verdict.MODEL_ESTIMATE: {"label": "Model estimate — not tested", "tier": "amber"},
    Verdict.NO_DIRECT_EVIDENCE: {"label": "No direct evidence", "tier": "grey"},
}

GravityKey = Literal["orbit", "microgravity", "earth", "1g", "moon", "mars"]


# ---------- errors ----------
class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorResponse(BaseModel):
    error: ErrorBody


# ---------- shared ----------
class Flag(BaseModel):
    text: str
    kind: Literal["quality_flag", "warning"] = "quality_flag"


class EvidenceRecord(BaseModel):
    """One NASA experiment row, verbatim fields + UI helpers. Null stays null ("not available")."""
    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    source_investigation: str | None = None
    psi_id: str | None = None
    doi: str | None = None
    gravity_level: str
    gravity_bucket: Literal["microgravity", "1g"]
    material_id: str | None = None
    material_variant: str | None = None
    fuel_material: str | None = None
    evidence_type: str
    configuration: str | None = None
    oxygen_pct: float | None = None
    oxygen_basis: str | None = None
    pressure_kpa: float | None = None
    airflow_cm_s: float | None = None
    airflow_note: str | None = None
    outcome_type: str | None = None
    outcome_variable: str | None = None
    outcome_value: float | str | None = None
    outcome_unit: str | None = None
    outcome_class: str | None = None
    uloi_pct: float | None = None
    flame_behavior_notes: str | None = None
    quality_flags: list[str] = Field(default_factory=list)
    source_ref: str | None = None
    source_file: str | None = None
    source_row: int | str | None = None
    license: str | None = None
    pair_id: str | None = None
    finding_ids: list[str] = Field(default_factory=list)
    flammability_relevant: bool = True
    # computed
    source_url: str | None = None
    display_kind: Literal["result", "tested_at", "observation", "threshold", "count", "smoke"]
    display_text: str = Field(description="One-line, UI-ready description built only from record fields")
    test_family: Literal["LOI_downward", "NASA_STD_6001_T1_upward"] | None = None
    distance: float | None = Field(None, description="Condition distance to the request (lower = closer)")
    similarity: float | None = Field(None, description="Vector similarity if matched by free-text question")


class EvidenceGroup(BaseModel):
    evidence_type: str
    label: str
    records: list[EvidenceRecord]
    total_in_group: int


class MaterialVariant(BaseModel):
    variant: str
    n_records: int
    inferred: bool = Field(description="True when the variant text says the material was not named in the source cell")


class MaterialCard(BaseModel):
    material_id: str
    name_en: str
    name_ar: str | None = None
    kind: str | None = None
    chemical_family: str | None = None
    aliases: list[str] = []
    variants: list[MaterialVariant] = []
    oxygen_pct_range: list[float | None] | None = None
    pressure_kpa_range: list[float | None] | None = None
    moc_pct_range_1g: list[float | None] | None = None
    uloi_pct_range_1g: list[float | None] | None = None
    gravity_levels: list[str] = []
    has_microgravity_evidence: bool
    has_1g_evidence: bool
    cross_gravity_group: str | None = None
    warnings: list[str] = []
    dois: list[str] = []


class MaterialMatch(BaseModel):
    material: MaterialCard
    score: float
    match_type: Literal["exact", "text", "vector"]
    confident: bool = Field(True, description="False = suggestion only; /api/assess never auto-resolves on these")


class MaterialSearchResponse(BaseModel):
    query: str
    matches: list[MaterialMatch]
    empty_state_message: str | None = None


class MaterialListResponse(BaseModel):
    materials: list[MaterialCard]
    total: int


class MaterialDetailResponse(BaseModel):
    material: MaterialCard
    stats: dict[str, int]
    warnings: list[str]


class MaterialEvidenceResponse(BaseModel):
    material_id: str
    groups: list[EvidenceGroup]
    smoke_detection: list[EvidenceRecord] = Field(default_factory=list, description="flammability_relevant=false (SAME): never burn evidence")
    empty_state_message: str | None = None


# ---------- presets ----------
class Preset(BaseModel):
    id: str
    name: str
    pressure_psia: float
    pressure_kpa: float
    o2_pct: float
    gravity: str
    source: str


class GravityLevel(BaseModel):
    key: str
    g: float
    bucket: Literal["microgravity", "1g", "none"]
    has_direct_data: bool
    note: str | None = None


class PresetsResponse(BaseModel):
    presets: list[Preset]
    gravity_levels: list[GravityLevel]


# ---------- assess ----------
class UnknownMaterialProps(BaseModel):
    polymer_family: str | None = None
    char_yield_pct: float | None = Field(None, ge=0, le=100)
    known_loi_pct: float | None = None
    known_loi_standard: str | None = None
    thickness_mm: float | None = None


class AssessRequest(BaseModel):
    material_query: str = Field(min_length=1)
    material_variant: str | None = None
    preset_id: str | None = None
    oxygen_pct: float | None = Field(None, ge=0, le=100)
    pressure_kpa: float | None = Field(None, ge=0)
    gravity: GravityKey = "orbit"
    airflow_cm_s: float | None = Field(None, ge=0)
    thickness_mm: float | None = None
    question: str | None = None
    unknown_material_props: UnknownMaterialProps | None = None
    use_llm: bool = Field(True, description="Allow the optional LLM summary (used only when ANTHROPIC_API_KEY is set; always number-checked)")

    @field_validator("material_query")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("material_query must not be blank")
        return v


class Tolerances(BaseModel):
    o2_pct: float
    pressure_kpa: float
    text: str = Field(description='e.g. "matched within ±1.5% O2 and ±20 kPa"')


class OneGBaseline(BaseModel):
    records: list[EvidenceRecord]
    moc_values: list[dict[str, Any]] = Field(description="[{experiment_id, moc_pct, uloi_pct, pressure_kpa, variant, source_url}] verbatim; never converted to LOI")
    test_note: str = "NASA-STD-6001 Test 1 (upward) MOC/ULOI — not comparable to LOI (downward, ASTM D2863)"
    standard_moc_values: list[float] = Field(default_factory=list, description="MOC % O2 of rows whose configuration states the standard Test 1 procedure")
    procedure_note: str | None = Field(None, description="Which rows are 'standard' and why (source: Hirsch et al. 2011)")


class EarthVsSpace(BaseModel):
    available: bool
    baseline_1g: OneGBaseline | None = None
    microgravity_evidence: list[EvidenceRecord] = []
    one_g_not_conservative: bool | None = None
    banner: str | None = Field(None, description="Red banner text when a µg sustained burn exists below the 1g MOC")
    banner_sources: list[EvidenceRecord] = []
    comparison_text: str | None = None
    correction_model_status: Literal["not_configured", "configured"] = "not_configured"
    correction_model_message: str | None = None
    empty_state_message: str | None = None


class Estimate(BaseModel):
    kind: Literal["model_estimate", "van_krevelen_loi_1g"]
    label: str
    value: float
    unit: str
    error: float | None = None
    error_unit: str | None = None
    inputs: dict[str, Any]
    equation: str
    citation: str
    page: str | None = None
    not_a_microgravity_limit: bool = False


class ModelValidationItem(BaseModel):
    investigation: str
    n: int
    model_brier: float
    baseline_brier: float
    model_accuracy: float
    baseline_accuracy: float


class ModelValidation(BaseModel):
    method: str = "leave-one-investigation-out"
    pooled_n: int
    model_brier: float
    baseline_brier: float
    model_accuracy: float
    baseline_accuracy: float
    beats_baseline: bool
    per_investigation: list[ModelValidationItem]
    statement: str


class BurnPrediction(BaseModel):
    """Model estimate of P(flame keeps burning) in microgravity. Never a tested result."""
    label: str = "Model estimate — not tested"
    role: Literal["estimate", "cross_check"] = Field(description="estimate: no tested record at these conditions; cross_check: a tested record exists, shown next to it")
    basis: Literal["no_research", "earth_only", "not_tested_at_these_conditions", "tested_here"] = Field(
        description="no_research: no data for this material at all; earth_only: only 1g data exists; not_tested_at_these_conditions: microgravity data exists elsewhere; tested_here: see role=cross_check")
    probability_sustained: float
    interval_95: tuple[float, float]
    material_group: str | None = Field(None, description="The model's material group, or null when the model has no coefficient for this material (prior spread, wide interval)")
    statement: str
    inputs: dict[str, Any]
    airflow_assumption: str | None = None
    trained_on: dict[str, Any]
    validation: ModelValidation
    oxygen_odds_ratio_per_point: list[float] = Field(description="[estimate, low95, high95]")
    caveats: list[str]


class NearestEvidence(BaseModel):
    gravity_bucket: Literal["microgravity", "1g"]
    record: EvidenceRecord
    delta_o2_pct: float | None = None
    delta_pressure_kpa: float | None = None
    note: str | None = None


class Finding(BaseModel):
    id: str
    claim: str
    page: int | str | None = None
    section: str | None = None
    safety_area: str | None = None


class InvestigationCard(BaseModel):
    accession: str
    acronym: str | None = None
    title: str
    doi: str | None = None
    objective: str | None = None
    hypothesis: str | None = None
    landing_page: str | None = None


class ScatterPoint(BaseModel):
    o2: float | None
    pressure_kpa: float | None
    gravity: Literal["microgravity", "1g", "requested"]
    outcome: str | None
    experiment_id: str | None = None
    is_requested_point: bool = False


class GapCell(BaseModel):
    material_id: str | None = None
    o2_pct: float | None = None
    pressure_kpa: float | None = None
    gravity: str | None = None
    suggested_test: str
    reason: str


class AssessResponse(BaseModel):
    verdict: Verdict
    verdict_label: str
    verdict_tier: Literal["green", "amber", "grey"]
    verdict_reason: str
    empty_state_message: str | None = None
    material: MaterialCard | None
    material_resolved_as: str | None = None
    requested: dict[str, Any]
    matched_tolerances: Tolerances
    evidence_groups: list[EvidenceGroup]
    smoke_detection: list[EvidenceRecord] = []
    earth_vs_space: EarthVsSpace | None = None
    estimate: Estimate | None = None
    burn_prediction: BurnPrediction | None = None
    nearest_evidence: list[NearestEvidence] = []
    findings: list[Finding] = []
    investigations: list[InvestigationCard] = []
    scatter_points: list[ScatterPoint] = []
    summary_text: str
    summary_source: Literal["llm_checked", "template"]
    summary_fallback_reason: str | None = Field(None, description="Why the LLM text was not used (only set when an LLM attempt was rejected or failed)")
    warnings: list[str] = []
    gaps: list[GapCell] = []


# ---------- coverage / gaps ----------
class CoverageResponse(BaseModel):
    material_id: str
    o2_axis: list[float] = Field(description="O2 % bin lower edges (1% bins)")
    pressure_axis: list[str] = Field(description='["<60","60-80","80-95",">95"] kPa')
    grids: dict[str, list[list[dict[str, int]]]] = Field(
        description='{"microgravity": grid[pressure_idx][o2_idx] = {"outcomes": n, "conditions_only": n}, "1g": ...}')
    preset_overlays: list[dict[str, Any]]
    empty_state_message: str | None = None


class NextExperiment(BaseModel):
    rank: int
    label: str = "Suggested test (not a result)"
    material_id: str
    o2_pct: float
    pressure_kpa: float
    gravity: str
    preset_id: str | None
    why: str
    score_parts: dict[str, float]
    bordering_evidence: list[str] = Field(description="experiment_ids bordering the empty cell")


class NextExperimentsResponse(BaseModel):
    preset: str | None
    suggestions: list[NextExperiment]
    empty_state_message: str | None = None


# ---------- validation / labels ----------
OutcomeLabel = Literal["sustained_burn", "brief_then_self_extinguished", "no_ignition",
                       "extinguished_by_flow_or_N2", "hardware_issue", "unclear"]


class LabelQueueItem(BaseModel):
    experiment_id: str
    material_id: str | None
    oxygen_pct: float | None
    pressure_kpa: float | None
    flame_behavior_notes: str | None
    suggested_label: OutcomeLabel | None
    suggestion_rule: str | None = None
    suggested_quote: str | None = Field(None, description="Verbatim sentence the keyword rule matched; a hint, not a decision")
    status: Literal["unlabelled", "suggested", "confirmed"]
    label: OutcomeLabel | None = Field(None, description="Human label (only when status = confirmed)")
    quote: str | None = None
    labelled_by: str | None = None


class LabelQueueResponse(BaseModel):
    total: int
    items: list[LabelQueueItem]


class LabelIn(BaseModel):
    experiment_id: str
    label: OutcomeLabel
    quote: str = Field(min_length=1, description="Supporting span copied from flame_behavior_notes")
    labelled_by: str = Field(min_length=1)


class LabelOut(LabelIn):
    status: Literal["suggested", "confirmed"]


class ValidationResponse(BaseModel):
    labels_confirmed: int
    labels_total_needed: int
    old_method_test: dict[str, Any]
    saffire_pairs: list[dict[str, Any]]
    correction_model: dict[str, Any]
    caveats: list[str]
    empty_state_message: str | None = None


# ---------- misc ----------
class DemoScenario(BaseModel):
    id: str
    title: str
    description: str
    request: AssessRequest


class DemoScenariosResponse(BaseModel):
    scenarios: list[DemoScenario]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    mock: bool
    db: dict[str, Any]
    vector_index: dict[str, Any]
    embedding_model: dict[str, Any]
    llm: dict[str, Any] = Field(default_factory=dict, description="Optional AI phrasing: provider/model in use, or provider null (template text only)")


class ExperimentDetailResponse(BaseModel):
    record: EvidenceRecord
    card_text: str | None = None
    source_url: str | None = None
    findings: list[Finding] = []
    investigation: InvestigationCard | None = None
    extra: dict[str, Any] | None = None
    smoke_only: bool = False


class AboutResponse(BaseModel):
    investigations: list[InvestigationCard]
    provenance: dict[str, Any]
    licenses: list[str]
    incidents: list[dict[str, Any]]
    earth_benefits: list[dict[str, Any]]


# ---------- frontend adapter endpoints: /api/experiments, /api/compare, /api/ask ----------
class ExperimentListItem(BaseModel):
    """Shape the frontend (src/components/api.ts `Experiment`) expects. Every value comes from the record; null stays null."""
    id: str
    program: str | None = None
    title: str
    material: str | None = None
    material_id: str | None = None
    gravity: str
    oxygen: str | None = None
    airflow: str | None = None
    year: int | None = None
    summary: str
    source_id: str | None = None
    source_url: str | None = None
    evidence_type: str | None = None
    display_kind: str | None = None
    quality_flags: list[str] = []
    flammability_relevant: bool = True


class ExperimentListResponse(BaseModel):
    experiments: list[ExperimentListItem]
    total: int
    returned: int


class CompareRequest(BaseModel):
    experiment_ids: list[str] = Field(min_length=2, max_length=12, description="The first id is the reference; every other record is checked against it.")
    use_llm: bool = True


class CompareItem(BaseModel):
    experiment_id: str
    comparable: bool
    reason: str
    differences: list[str] = []


class ScientificLimitation(BaseModel):
    id: str
    category: Literal["experimental_conditions", "data_coverage", "measurement_uncertainty", "methodology", "interpretation", "other"]
    severity: Literal["info", "caution", "critical"] = "info"
    title: str
    description: str
    affected_experiment_ids: list[str] = []
    source_ids: list[str] = []
    source_urls: list[str] = []


class SourceRef(BaseModel):
    source_id: str
    title: str
    url: str | None = None


class ComparisonResponse(BaseModel):
    summary: str
    reference_id: str
    items: list[CompareItem]
    limitations: list[ScientificLimitation]
    methodology: str
    sources: list[SourceRef]
    generated_at: str
    summary_source: Literal["template", "llm_checked"] = "template"
    summary_fallback_reason: str | None = None


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    experiment_ids: list[str] = Field(default=[], max_length=12, description="Optional: answer only from these records.")
    use_llm: bool = True


class AskResponse(BaseModel):
    answer: str
    limitations: str | None = None
    citations: list[SourceRef]
    records: list[EvidenceRecord] = []
    answer_source: Literal["template", "llm_checked"] = "template"
    answer_fallback_reason: str | None = None
