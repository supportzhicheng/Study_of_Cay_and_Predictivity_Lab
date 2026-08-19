"""Registry of normalized quarterly source contracts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpec:
    """Static contract and provenance for one normalized source."""

    source_id: str
    filename_stem: str
    required_columns: tuple[str, ...]
    provider: str
    access_class: str
    required_for_panel: bool = True


SOURCE_REGISTRY = {
    "paper_macro": SourceSpec(
        source_id="paper_macro",
        filename_stem="paper_macro_quarterly",
        required_columns=("paper_c", "paper_a", "paper_y", "posted_cay"),
        provider="Lettau and Ludvigson author archive",
        access_class="public",
    ),
    "core_macro": SourceSpec(
        source_id="core_macro",
        filename_stem="core_macro_quarterly",
        required_columns=("c", "a", "y"),
        provider="BEA, Federal Reserve, and FRED",
        access_class="public",
    ),
    "sp_market": SourceSpec(
        source_id="sp_market",
        filename_stem="sp_market_quarterly",
        required_columns=(
            "sp_real_return",
            "sp_excess_return",
            "dividend_yield",
            "payout_ratio",
        ),
        provider="Robert Shiller",
        access_class="public",
    ),
    "crsp_market": SourceSpec(
        source_id="crsp_market",
        filename_stem="crsp_market_quarterly",
        required_columns=(
            "crsp_vw_real_return",
            "crsp_vw_excess_return",
            "bill_30d_return",
        ),
        provider="WRDS/CRSP",
        access_class="licensed",
    ),
    "rates": SourceSpec(
        source_id="rates",
        filename_stem="rates_quarterly",
        required_columns=(
            "bill_3m_return",
            "relative_bill_rate_30d",
            "relative_bill_rate_3m",
            "term_spread_10y_3m",
            "term_spread_10y_1y",
            "default_spread",
        ),
        provider="FRED",
        access_class="public",
    ),
    "recessions": SourceSpec(
        source_id="recessions",
        filename_stem="recessions_quarterly",
        required_columns=("nber_recession",),
        provider="FRED/NBER",
        access_class="public",
    ),
    "posted_cay": SourceSpec(
        source_id="posted_cay",
        filename_stem="posted_cay_quarterly",
        required_columns=("cay",),
        provider="Lettau and Ludvigson author site",
        access_class="public",
        required_for_panel=False,
    ),
}


def get_source_spec(source_id: str) -> SourceSpec:
    """Return a registered source or reject an unknown identifier."""
    try:
        return SOURCE_REGISTRY[source_id]
    except KeyError as exc:
        valid = ", ".join(sorted(SOURCE_REGISTRY))
        raise ValueError(
            f"Unknown source '{source_id}'. Valid sources: {valid}"
        ) from exc


def required_panel_sources() -> tuple[str, ...]:
    """Return the six source families required by the core panel."""
    return tuple(
        source_id
        for source_id, spec in SOURCE_REGISTRY.items()
        if spec.required_for_panel
    )
