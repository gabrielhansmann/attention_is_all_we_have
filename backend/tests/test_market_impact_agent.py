"""Local matching, provenance and source counts: no database or external model calls."""
import pytest

from app.agents import market_impact_agent as agent
from app.knowledge import tools


def feedback(id, market, polarity, count=1, line="G60", text=None):
    text = text or f"Seat ventilation comment {id}"
    return tools.Hit(tools.Citation("feedback", id, "feedback.xlsx", f"row {id}", "Seat ventilation comment"),
                     text, {"vehicle_line": line, "market_code": market,
                                                  "polarity": polarity, "polarity_count": count})


@pytest.fixture
def local_store(monkeypatch):
    monkeypatch.setattr(tools, "_embed", lambda *args: pytest.fail("must not send feature data to an external model"))
    monkeypatch.setattr(tools, "search_feedback", lambda *args, **kwargs: pytest.fail("must use local matching"))
    monkeypatch.setattr(tools, "feedback_stats", lambda *args, **kwargs: [
        {"key": "US", "n": 100}, {"key": "EU", "n": 40}, {"key": "RoW", "n": 6}])


def test_feature_passages_overrule_whole_comment_polarity_and_preserve_tradeoffs(local_store, monkeypatch):
    hits = [feedback("1", "US", "negative", 2, text="Seat ventilation is excellent but the screen is poor"), feedback("2", "US", "positive", 50, text="Seat ventilation is weak"),
            feedback("3", "EU", "negative", 8, text="I wish this car had seat ventilation"), feedback("4", "EU", "positive", 3, text="Seat ventilation is great"),
            feedback("5", "RoW", "positive", 2, text="Seat ventilation is great"), feedback("6", "RoW", "negative", 2, text="Seat ventilation is weak")]
    seen = {}

    def query(terms, **kwargs):
        seen.update(terms=terms, **kwargs)
        return hits

    monkeypatch.setattr(tools, "feature_feedback", query)
    result = agent.assess("G60", feature="Seat ventilation")
    markets = {m["market"]: m for m in result["markets"]}
    assert markets["US"]["direction"] == "mixed" and markets["US"]["matched_total"] == 52
    assert markets["US"]["signal_counts"] == {"benefit": 1, "risk": 1, "unclear": 0}
    assert markets["EU"]["direction"] == "positive" and markets["EU"]["counts"]["negative"] == 8
    assert markets["RoW"]["direction"] == "mixed"
    assert markets["CN"]["direction"] == "insufficient" and "No customer feedback" in markets["CN"]["explanation"]
    assert markets["US"]["evidence"][0]["citation"]["file"] == "feedback.xlsx"
    assert seen["line"] == "G60" and seen["limit_per_market"] == 12
    assert "cooled seats" in seen["terms"]
    assert "do not determine direction or market share" in result["basis"]
    assert "share" not in markets["US"]


def test_deduplicates_evidence_and_rejects_other_lines_or_markets(local_store, monkeypatch):
    hit = feedback("1", "US", "positive", 4)
    monkeypatch.setattr(tools, "feature_feedback", lambda *args, **kwargs: [
        hit, hit, feedback("2", "US", "negative", 80, line="F70"), feedback("3", "MARS", "negative", 80)])
    result = agent.assess("G60", feature="Seat ventilation")
    assert result["markets"][0]["matched_total"] == 4
    assert len(result["markets"][0]["evidence"]) == 1


def test_resolves_catalog_label_on_the_requested_line(local_store, monkeypatch):
    option = tools.Hit(tools.Citation("option", "chosen", "catalog.pdf", "SA 453", "Sitzbelüftung"),
                       "Sitzbelüftung", {"vehicle_line": "G60"})
    monkeypatch.setattr(tools, "get_options", lambda **kwargs: [option])
    monkeypatch.setattr(tools, "feature_feedback", lambda *args, **kwargs: [])
    result = agent.assess("G60", option_id="chosen")
    assert result["feature"] == "Sitzbelüftung" and "ventilated seats" in result["query_terms"]
    assert result["catalog_citation"]["id"] == "chosen"
    assert all(m["direction"] == "insufficient" for m in result["markets"])
    with pytest.raises(LookupError):
        agent.assess("G60", option_id="unknown")


def test_unknown_feature_does_not_expand_into_unrelated_generic_words():
    assert agent.feature_terms("Adaptive comfort package") == ["adaptive comfort package"]


def test_local_query_is_parameterized_and_never_uses_embeddings(monkeypatch):
    seen = {}

    class Connection:
        def execute(self, query, params):
            seen.update(query=query, params=params)
            return self

        def fetchall(self):
            return []

    monkeypatch.setattr(tools, "_conn", lambda: Connection())
    monkeypatch.setattr(tools, "_embed", lambda *args: pytest.fail("no external embeddings"))
    assert tools.feature_feedback(["seat ventilation", ".*' OR 1=1"], line="G60") == []
    assert ".*' OR 1=1" not in seen["query"]
    assert seen["params"]["line"] == "G60"
    assert seen["params"]["patterns"][1].startswith(r"\.\*")
    assert tools.feature_feedback([], line="G60") == []
    with pytest.raises(ValueError):
        tools.feature_feedback(["seat"], line="G60", limit_per_market=100)


@pytest.mark.parametrize("text,stance", [
    ('The 19 inch wheels are terrific. Not having old-style knobs is a serious shortcoming.', 'supports'),
    ('I wish this car had seat ventilation.', 'supports'),
    ('Seat ventilation is missing.', 'supports'),
    ('Seat ventilation is too expensive.', 'risk'),
    ('Seat ventilation does not work.', 'risk'),
    ('Seat ventilation was included in the package.', 'unclear'),
    ('Seat ventilation is not great.', 'risk'),
    ('I do not want seat ventilation.', 'risk'),
    ('I do not hate seat ventilation.', 'unclear'),
    ('I prefer seat ventilation.', 'supports'),
    ('The screen is great but seat ventilation is weak.', 'risk'),
    ('Seat ventilation is great but seat ventilation is too noisy.', 'mixed'),
    ('Seat ventilation could be better.', 'risk'),
    ('Seat ventilation needs to work better.', 'risk'),
    ('Seat ventilation is not needed.', 'risk'),
    ('I never use seat ventilation.', 'risk'),
])
def test_comment_reason_attaches_to_feature_not_unrelated_equipment(text, stance):
    feature = '19" wheels' if '19 inch' in text else 'Seat ventilation'
    actual, reason, excerpt = agent.comment_signal(text, agent.feature_terms(feature))
    assert actual == stance and excerpt in text and reason


def test_comfort_topic_alone_does_not_imply_praise():
    assert agent.comment_signal('Seat comfort was evaluated.', agent.feature_terms('Comfort seats'))[0] == 'unclear'


def test_mixed_excerpt_shows_both_feature_passages_or_explains_the_excerpt_limit():
    text = 'Seat ventilation is great but seat ventilation is too noisy.'
    stance, reason, quote = agent.comment_signal(text, agent.feature_terms('Seat ventilation'))
    assert stance == 'mixed' and 'great' in quote and 'too noisy' in quote and quote in text
    text = 'Seat ventilation is great. ' + 'Unrelated context. ' * 25 + 'Seat ventilation is too noisy.'
    stance, reason, quote = agent.comment_signal(text, agent.feature_terms('Seat ventilation'))
    assert stance == 'mixed' and quote in text and len(quote) <= 300
    assert 'open the source to review both' in reason
