from fibr0.config import Settings
from fibr0.models import AnalysisResult, Event, Slot, TickerImpact
from fibr0.stages import publish

SETTINGS = Settings(database_url=None, model="claude-opus-5", dry_run=True, fixture=None)


def event(tiers):
    return Event(
        id=7,
        slot=Slot.PRE_OPEN,
        title="t",
        text_for_analysis="x",
        source_urls=["https://x/1"],
        source_tiers=tiers,
    )


def result(summary: str, rationale: str = "Margins widen for peers.") -> AnalysisResult:
    return AnalysisResult(
        event_summary="s",
        category="supply_disruption",
        rationale_raw="raw",
        rationale_summary=summary,
        impacts=[
            TickerImpact(
                ticker="vlo",
                direction="up",
                horizon="1d",
                magnitude="medium",
                order="second",
                confidence=0.68,
                rationale=rationale,
            )
        ],
    )


def test_compound_banned_word_in_summary_blocks_event():
    kept, blocked = publish.build_predictions(
        event([1]), result("Peers gain margin. Effect is short-lived."), {}, SETTINGS
    )
    # "short-lived" contains the banned word "short", so this must be blocked.
    assert kept == [] and len(blocked) == 1


def test_clean_summary_passes_and_uppercases_ticker():
    kept, blocked = publish.build_predictions(
        event([1]), result("Peers gain margin. Effect is brief."), {}, SETTINGS
    )
    assert blocked == []
    assert kept[0].ticker == "VLO"
    assert kept[0].calibrated_confidence == 0.68
    assert not kept[0].is_calibrated


def test_unknown_ticker_is_blocked():
    kept, blocked = publish.build_predictions(
        event([1]), result("Peers gain margin. Effect is brief."), {}, SETTINGS, universe={"XOM"}
    )
    assert kept == []
    assert "not in ticker universe" in blocked[0]


def test_tier3_only_event_is_capped():
    kept, _ = publish.build_predictions(
        event([3]), result("Peers gain margin. Effect is brief."), {}, SETTINGS
    )
    assert kept[0].calibrated_confidence == 0.6
