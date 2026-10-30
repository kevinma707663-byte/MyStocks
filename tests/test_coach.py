"""
Automatic checks for the AI trading coach (core/coach.py).

They never call the real AI. A pretend client hands back a ready-made
answer, so the checks are free, fast, and give the same result every time.
Run them with:  python -m pytest tests
"""
import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from core import coach
from core import portfolio as pf
from core import warnings_sidebar as ws


# ===========================================================================
# A PRETEND CLAUDE
# ===========================================================================

class FakeClient:
    """Looks like anthropic.Anthropic() to coach_note(), but answers from a script."""

    def __init__(self, answer=None, error=None, stop_reason="end_turn", raw_text=None):
        self.answer, self.error, self.stop_reason, self.raw_text = answer, error, stop_reason, raw_text
        self.calls = []                                   # every request it was sent
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **request):
        self.calls.append(request)
        if self.error:
            raise self.error
        text = self.raw_text if self.raw_text is not None else json.dumps(self.answer)
        # A real answer holds an (empty) thinking block before the text.
        return SimpleNamespace(stop_reason=self.stop_reason,
                               content=[SimpleNamespace(type="thinking", thinking=""),
                                        SimpleNamespace(type="text", text=text)])


FOMO_WARNING = {"trap": "Chasing (FOMO)", "level": "caution",
                "message": "It's up 41.7% in about 3 months.",
                "tip": "Would you still buy it if it hadn't moved?"}

REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def response(status):
    return httpx2.Response(status, request=REQUEST)


def ask(answer=None, reason="", found=(FOMO_WARNING,), **fake):
    """Ask the coach about buying 10 NVDA at $200, with a pretend client."""
    client = FakeClient(answer=answer, **fake)
    result = coach.coach_note(pf.empty_portfolio(), "buy", "nvda", 10, 200,
                              reason=reason, found=list(found), client=client)
    return result, client


# ===========================================================================
# A GOOD NOTE
# ===========================================================================

def test_a_good_note_comes_back_with_its_disclaimer():
    result, _ = ask({"note": "It's up about 42% in three months. Would you buy it if it hadn't moved?",
                     "biases": []})
    assert result["status"] == "ok"
    assert result["note"].startswith("It's up about 42%")     # 41.7 rounded is allowed
    assert result["disclaimer"] == coach.DISCLAIMER


def test_a_bias_counts_only_if_the_quote_is_really_in_their_words():
    reason = "Everyone’s buying it and I can't miss out"      # curly apostrophe, like a phone types
    result, _ = ask({"note": "You sound rushed. What's your own reason?",
                     "biases": [{"bias": "Following the crowd", "quote": "Everyone's buying it"},
                                {"bias": "Acting on a tip", "quote": "my cousin said so"}]},
                    reason=reason)
    assert [b["bias"] for b in result["biases"]] == ["Following the crowd"]
    assert result["biases"][0]["meaning"] == coach.BIASES["Following the crowd"]


# ===========================================================================
# THE HONESTY CHECKS
# ===========================================================================

def test_a_made_up_number_throws_the_note_away():
    result, _ = ask({"note": "Analysts expect it to rise 73% next year!", "biases": []})
    assert result["status"] == "unavailable"
    assert result["note"] is None
    assert "number" in result["why"]


def test_numbers_from_the_facts_are_allowed():
    facts = {"trade": {"value": 2000.0}, "rule_warnings": [{"message": "It's up 41.7% in about 3 months."}]}
    assert coach._unknown_numbers("That's $2,000, and it's up 42% in 3 months.", facts) == []
    assert coach._unknown_numbers("It could double to 400.", facts) == ["400"]
    # Repeating the investor's own number back is fine.
    assert coach._unknown_numbers("You said you lost $3,500.", facts) == ["3,500"]
    assert coach._unknown_numbers("You said you lost $3,500.", facts, reason="I lost $3,500 last month") == []


def test_the_real_anthropic_library_accepts_the_request():
    """The real library, with only the internet faked: catches a setting it doesn't know."""
    sent = {}

    def pretend_internet(request):
        sent["body"] = json.loads(request.content)
        sent["beta"] = request.headers.get("anthropic-beta")
        answer = {"note": "Looks calm. What made you pick today?", "biases": []}
        return httpx2.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant", "model": coach.MODEL,
            "content": [{"type": "thinking", "thinking": "", "signature": "sig"},
                        {"type": "text", "text": json.dumps(answer)}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 900, "output_tokens": 60}})

    client = anthropic.Anthropic(api_key="test-key", max_retries=0, http_client=anthropic.DefaultHttpxClient(
        transport=httpx2.MockTransport(pretend_internet)))
    result = coach.coach_note(pf.empty_portfolio(), "buy", "KO", 5, 90, found=[], client=client)
    assert result["status"] == "ok"
    assert sent["beta"] == "server-side-fallback-2026-07-01"
    assert sent["body"]["output_config"]["format"]["type"] == "json_schema"


def test_the_request_keeps_facts_and_reason_in_separate_boxes():
    _, client = ask({"note": "Looks calm.", "biases": []}, reason="Long-term hold for my TFSA")
    request = client.calls[0]
    assert request["model"] == coach.MODEL
    assert request["fallbacks"] == "default"
    message = request["messages"][0]["content"]
    assert "<facts>" in message and "<reason>\nLong-term hold for my TFSA\n</reason>" in message
    assert '"ticker": "NVDA"' in message                         # tidied, like the rest of the app


# ===========================================================================
# NEVER BREAKS THE APP
# ===========================================================================

def test_no_api_key_means_the_coach_is_off(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = coach.coach_note(pf.empty_portfolio(), "buy", "KO", 5, 90, found=[])
    assert result["status"] == "off"
    assert "ANTHROPIC_API_KEY" in result["why"]


@pytest.mark.parametrize("error, status, words", [
    (anthropic.AuthenticationError("bad key", response=response(401), body=None), "off", "isn't valid"),
    (anthropic.RateLimitError("busy", response=response(429), body=None), "unavailable", "busy"),
    (anthropic.APITimeoutError(request=REQUEST), "unavailable", "couldn't connect"),
    (anthropic.InternalServerError("oops", response=response(500), body=None), "unavailable", "Anthropic's side"),
])
def test_api_problems_give_a_plain_message_not_an_error(error, status, words):
    result, _ = ask(error=error)
    assert result["status"] == status
    assert words in result["why"]


def test_a_refusal_or_a_garbled_answer_gives_no_note():
    refused, _ = ask({"note": "x", "biases": []}, stop_reason="refusal")
    garbled, _ = ask(raw_text="not json at all")
    assert refused["status"] == garbled["status"] == "unavailable"


def test_bad_inputs_still_get_the_apps_usual_messages():
    with pytest.raises(ValueError, match="Shares must be a number"):
        coach.coach_note(pf.empty_portfolio(), "buy", "KO", "ten", 90, found=[], client=FakeClient())


# ===========================================================================
# THE STREAMLIT EXAMPLE FROM THE NOTEBOOK (Chunk 7's partner example)
# ===========================================================================

COACH_FORM_APP = '''
import streamlit as st
from core import coach, portfolio as pf
from core import warnings_sidebar as ws

if "portfolio" not in st.session_state:
    st.session_state.portfolio = pf.empty_portfolio()
portfolio = st.session_state.portfolio

with st.form("trade"):
    action = st.radio("Action", ["buy", "sell"], horizontal=True)
    ticker = st.text_input("Ticker")
    shares = st.number_input("Shares", min_value=0.0)
    price = st.number_input("Price", min_value=0.0)
    reason = st.text_area("Why are you making this trade? (optional)")
    if st.form_submit_button("Check this trade"):
        try:
            found = ws.check_trade(portfolio, action, ticker, shares, price)
            with st.spinner("Your coach is thinking..."):
                tip = coach.coach_note(portfolio, action, ticker, shares, price, reason=reason, found=found)
            st.session_state.pending_trade = {"action": action, "ticker": ticker, "shares": shares, "price": price}
            st.session_state.pending_warnings = found
            st.session_state.pending_tip = tip
        except ValueError as error:
            st.error(str(error))

pending = st.session_state.get("pending_trade")
if pending:
    tip = st.session_state.pending_tip
    if tip["status"] == "ok":
        st.info(tip["note"])
        st.caption(tip["disclaimer"])
    else:
        st.caption(tip["why"])
    found = st.session_state.pending_warnings
    if st.button("Record it anyway" if found else "Record it"):
        ws.trade(portfolio, **pending)
        st.success("Recorded.")
        del st.session_state["pending_trade"]
'''


def test_streamlit_coach_note_shows_and_the_trade_still_records(monkeypatch):
    from streamlit.testing.v1 import AppTest
    # No market data or real AI needed for this test. monkeypatch puts the
    # real functions back afterwards, so later tests aren't affected.
    monkeypatch.setattr(ws, "check_trade", lambda *args, **kwargs: [])
    monkeypatch.setattr(coach, "coach_note", lambda *args, **kwargs: {
        "status": "ok", "note": "Looks calm. Why today?", "biases": [], "why": "", "disclaimer": "AI can be wrong."})
    app = AppTest.from_string(COACH_FORM_APP).run()
    app.text_input[0].input("KO")
    app.number_input[0].set_value(5)
    app.number_input[1].set_value(90)
    app.text_area[0].input("Long-term dividend buy")
    app.button[0].click().run()                          # "Check this trade"
    assert app.info[0].value == "Looks calm. Why today?"
    record = [b for b in app.button if b.label.startswith("Record")]
    record[0].click().run()                              # "Record it"
    assert len(app.session_state.portfolio["holdings"]) == 1
