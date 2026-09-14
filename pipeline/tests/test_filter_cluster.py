from fibr0.models import RawItem, Slot
from fibr0.stages import cluster, filter

UNIVERSE = [
    {"ticker": "XOM", "name": "Exxon Mobil Corp"},
    {"ticker": "VLO", "name": "Valero Energy Corp"},
]


def item(title: str, body: str = "", source: str = "src", tier: int = 2, id_: int = 0) -> RawItem:
    return RawItem(
        id=id_,
        source_id=source,
        url=f"https://x/{id_}",
        url_hash=str(id_),
        title=title,
        body=body,
        tier=tier,
    )


def test_filter_passes_energy_keywords_and_universe_names():
    m = filter.build_matcher(UNIVERSE)
    assert filter.is_relevant(item("Brent crude rises on OPEC cut"), m)
    assert filter.is_relevant(item("Exxon reports quarterly results"), m)
    assert filter.is_relevant(item("Shares of VLO jump"), m)


def test_filter_rejects_unrelated_news():
    m = filter.build_matcher(UNIVERSE)
    assert not filter.is_relevant(item("Local bakery wins award for sourdough"), m)


def test_cluster_groups_same_story_and_separates_different_ones():
    items = [
        item("Fire shuts crude unit at Texas Gulf Coast refinery", id_=1, tier=1),
        item("Texas Gulf Coast refinery crude unit shut after fire", id_=2, tier=2),
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
