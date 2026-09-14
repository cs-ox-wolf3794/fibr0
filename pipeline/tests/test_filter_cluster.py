from datetime import UTC, datetime, timedelta

from fibr0.models import RawItem, Slot
from fibr0.stages import cluster, filter

UNIVERSE = [
    {"ticker": "XOM", "name": "Exxon Mobil Corp"},
    {"ticker": "VLO", "name": "Valero Energy Corp"},
    {"ticker": "AR", "name": "Antero Resources Corp"},
]
NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


def item(
    title: str,
    body: str = "",
    source: str = "prnewswire_energy",
    tier: int = 2,
    id_: int = 0,
    age_hours: float = 1.0,
) -> RawItem:
    return RawItem(
        id=id_,
        source_id=source,
        url=f"https://x/{id_}",
        url_hash=str(id_),
        title=title,
        body=body,
        tier=tier,
        published_at=NOW - timedelta(hours=age_hours),
    )


def matcher():
    return filter.build_matcher(UNIVERSE)


def test_company_name_passes_from_any_source():
    m = matcher()
    assert filter.classify(item("Exxon reports quarterly results"), m, NOW) == "company"
    assert filter.classify(item("Valero shuts unit", source="fedreg_ferc"), m, NOW) == "company"


def test_short_ticker_is_not_matched_as_a_word():
    # "AR" is Antero's ticker but also an ordinary token; only the name should match.
    m = matcher()
    assert filter.classify(item("New AR headset launches"), m, NOW) is None
    assert filter.classify(item("Antero Resources raises output"), m, NOW) == "company"


def test_event_phrase_passes_even_for_strict_sources():
    m = matcher()
    assert filter.classify(item("Force majeure declared at Gulf terminal"), m, NOW) == "event"
    assert (
        filter.classify(
            item("Commission approves certificate for pipeline", source="fedreg_ferc"), m, NOW
        )
        == "event"
    )


def test_two_weak_terms_pass_only_for_non_strict_sources():
    m = matcher()
    title = "Crude and natural gas prices diverge"
    assert filter.classify(item(title, source="googlenews_energy"), m, NOW) == "domain"
    assert filter.classify(item(title, source="fedreg_doe"), m, NOW) is None
    assert filter.classify(item(title, source="nrc_news"), m, NOW) is None


def test_single_weak_term_is_not_enough():
    m = matcher()
    assert filter.classify(item("Local bakery switches to solar"), m, NOW) is None


def test_procedural_notices_are_excluded():
    m = matcher()
    assert (
        filter.classify(
            item(
                "Commission Information Collection Activities; Comment Request",
                source="fedreg_ferc",
            ),
            m,
            NOW,
        )
        is None
    )
    assert (
        filter.classify(
            item("Douglas Weaver sworn in as NRC Commissioner", source="nrc_news"), m, NOW
        )
        is None
    )


def test_old_items_are_dropped():
    m = matcher()
    assert filter.classify(item("Exxon reports quarterly results", age_hours=48), m, NOW) is None


def test_routine_disclosures_and_marketing_are_excluded():
    m = matcher()
    for title in (
        "ASML reports transactions under its current share buyback program",
        "ASM share buyback update September 7 - 11, 2026",
        "Gastech 2026 Opens in Bangkok with a Clear Message",
        "Atlantic Tropical Weather Outlook",
        "Valero to present at Barclays energy conference",
        "Exxon names new chief financial officer",
    ):
        assert filter.classify(item(title, source="globenewswire_energy"), m, NOW) is None, title


def test_pr_wires_need_company_or_event_not_just_domain_terms():
    m = matcher()
    title = "Crude and natural gas outlook for the decade"
    assert filter.classify(item(title, source="prnewswire_oilgas"), m, NOW) is None
    assert filter.classify(item(title, source="googlenews_energy"), m, NOW) == "domain"
    assert (
        filter.classify(
            item("Force majeure declared at Gulf terminal", source="prnewswire_oilgas"), m, NOW
        )
        == "event"
    )


def test_items_without_date_are_kept():
    m = matcher()
    i = item("Exxon reports quarterly results")
    i.published_at = None
    assert filter.classify(i, m, NOW) == "company"


def test_edgar_passes_only_on_universe_company():
    m = matcher()
    assert (
        filter.classify(
            item("8-K - PBF Energy Inc. (0001534504) (Filer)", source="sec_edgar_8k"), m, NOW
        )
        is None
    )
    assert (
        filter.classify(
            item("8-K - Valero Energy Corp (0001035002) (Filer)", source="sec_edgar_8k"), m, NOW
        )
        == "company"
    )
    # "Acquisition" is an event phrase, but a SPAC filing is not an energy event.
    assert (
        filter.classify(
            item(
                "8-K - Embrace Change Acquisition Corp. (0001869601) (Filer)", source="sec_edgar_8k"
            ),
            m,
            NOW,
        )
        is None
    )


def test_cluster_merges_one_story_with_different_wording():
    titles = [
        "Oil prices jump after Saudi Arabia shuts East-West pipeline - Yahoo Finance",
        "Saudi Arabia Shuts Key East-West Pipeline Following Attacks, Escalating Energy Crunch - X",
        "Saudi pipeline hit by drones will be out of service for weeks, restricting oil flow - AP",
        "Exxon Mobil shuts down Joliet refinery after power outage - Reuters",
    ]
    groups = cluster.cluster([item(t, id_=i) for i, t in enumerate(titles)])
    ids = [sorted(m.id for m in g) for g in groups]
    assert [0, 1] in ids or [0, 1, 2] in ids, ids
    assert [3] in ids


def test_cluster_groups_same_story_across_outlets():
    items = [
        item("Fire shuts crude unit at Texas Gulf Coast refinery - Reuters", id_=1, tier=1),
        item("Texas Gulf Coast refinery crude unit shut after fire - Bloomberg", id_=2, tier=2),
        item("FERC approves natural gas pipeline expansion", id_=3, tier=1),
    ]
    groups = cluster.cluster(items)
    assert len(groups) == 2
    assert {i.id for i in groups[0]} == {1, 2}


def test_to_event_uses_highest_trust_title_and_keeps_all_urls():
    members = [
        item("Wire headline about refinery fire", id_=2, tier=2, source="wire"),
        item("Official statement on refinery fire", id_=1, tier=1, source="official"),
    ]
    event = cluster.to_event(members, Slot.PRE_OPEN)
    assert event.title == "Official statement on refinery fire"
    assert set(event.source_urls) == {"https://x/1", "https://x/2"}
    assert event.source_tiers == [1, 2]
    assert not event.tier3_only
