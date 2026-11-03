"""Opening chat: a friendly guide asks four quick questions so the app can fit the person.

This is SCRIPTED, not AI: no API key, no cost, and it can never say anything off-script (so it can't
drift into financial advice). Answers are tappable buttons, which also suits a phone.
Everything is kept only in this visitor's session (st.session_state). Nothing is saved or sent anywhere.
Frontend only: nothing here touches core/."""
import streamlit as st

from app import mascot

GUIDE = "Fin"        # the character's name: change it here
AVATAR = "🧭"

QUESTIONS = [
    {"key": "experience",
     "ask": f"Hi, I'm {GUIDE}! I'll ask 4 quick questions so this app fits you. First: how long have you been investing?",
     "options": [("new", "Just starting out"), ("some", "1 to 3 years"), ("long", "More than 3 years")],
     "reply": {"new": "Welcome! I'll explain the words as we go.",
               "some": "Nice, you've seen a few ups and downs by now.",
               "long": "Great, you'll know a lot of this already. I'll keep it light."}},
    {"key": "goal",
     "ask": "What are you mainly after?",
     "options": [("grow", "Growing my money over the long run"), ("trade", "Making money on stock moves"),
                 ("protect", "Not losing what I have"), ("learn", "Learning how it all works")],
     "reply": {"grow": "Got it: the long game.",
               "trade": "Plenty of people treat stocks a bit like a bet. I'll help you see the risks behind each one.",
               "protect": "Understood. I'll point you to the risk checks.",
               "learn": "Perfect. Every screen explains itself."}},
    {"key": "drop",
     "ask": "Imagine your portfolio fell 20% in a month. What would you most likely do?",
     "options": [("sell", "Sell some to stop the pain"), ("hold", "Worry, but hold on"),
                 ("buy", "Buy more while it's cheaper")],
     "reply": {"sell": "Honest answer, and very human. I'll compare it with how bumpy your portfolio has really been.",
               "hold": "That takes nerve. I'll compare it with how bumpy your portfolio has really been.",
               "buy": "Bold! I'll compare it with how bumpy your portfolio has really been."}},
    {"key": "decide",
     "ask": "Last one: how do you usually decide what to buy?",
     "options": [("tips", "Tips from friends or social media"), ("news", "News and what's trending"),
                 ("research", "My own research"), ("plan", "A set plan or index funds")],
     "reply": {"tips": "Thanks for being straight about it. Tips are one of the most common traps, so I'll watch for it.",
               "news": "Fair. News moves prices fast, which is worth knowing about.",
               "research": "Good. I'll give you more to research with.",
               "plan": "A plan is a strong habit. I'll help you check it."}},
]

# What each answer means for the app (design choices of this frontend, not backend rules).
# Starting values that the person can change on the Improve tab.
DROP_STARTING_POINT = {"sell": 15, "hold": 25, "buy": 35}      # "biggest fall you'd accept (%)"


def finished() -> bool:
    return st.session_state.get("profile") is not None


def profile() -> dict:
    return st.session_state.get("profile") or {}


def reset():
    ss = st.session_state
    ss.profile, ss.chat = None, {"i": 0, "answers": {}}


def _last_reply():
    """Fin's reaction to the most recent answer, if any."""
    answers = st.session_state.get("chat", {}).get("answers", {})
    for q in reversed(QUESTIONS):
        if q["key"] in answers:
            return q["reply"][answers[q["key"]]]
    return ""


def _say(text):
    """Fin speaks: animated mouth + typed bubble, and out loud if the visitor switched voice on."""
    mascot.stage(text, voice=bool(st.session_state.get("fin_voice")))
    st.toggle("🔊 Let Fin talk out loud", key="fin_voice",
              help="Uses your browser's built-in voice. If nothing plays, tap 'Hear Fin' on the speech bubble.")


def render():
    """Fin asks the questions. Returns True when the chat is over."""
    ss = st.session_state
    ss.setdefault("chat", {"i": 0, "answers": {}})
    chat = ss.chat
    if chat["i"] < len(QUESTIONS):
        q = QUESTIONS[chat["i"]]
        said = [dict(x["options"])[chat["answers"][x["key"]]] for x in QUESTIONS if x["key"] in chat["answers"]]
        _say((_last_reply() + " " if _last_reply() else "") + q["ask"])
        if said:
            st.caption("You said: " + "  ·  ".join(said))
        for value, label in q["options"]:
            if st.button(label, key=f"chat_{q['key']}_{value}", width="stretch"):
                chat["answers"][q["key"]] = value
                chat["i"] += 1
                if chat["i"] >= len(QUESTIONS):
                    ss.profile = dict(chat["answers"])
                st.rerun()
        if st.button("Skip the questions", key="chat_skip", type="tertiary"):
            ss.profile = {}
            st.rerun()
        return False
    return True


def starting_point(risk_report):
    """A short, personal 'Start here' card for the Overview. Facts come from the real risk report."""
    p = profile()
    if not p:
        return None
    lines = []
    goal = p.get("goal")
    lines.append({"grow": "You're playing the long game: the <b>Risk</b> tab shows what could slow it down.",
                  "trade": "You like acting on stock moves: use <b>Alerts</b> to check a trade (and write down why) before you place it.",
                  "protect": "You want to protect what you have: start with the <b>Risk</b> tab, then <b>Improve</b> with the lowest-risk goal.",
                  "learn": "You're here to learn: every tab has a tip at the top and a <b>Words explained</b> section at the bottom."}.get(goal, ""))
    drop = p.get("drop")
    if drop and risk_report is not None and len(risk_report.get("underwater", [])):
        worst = abs(float(risk_report["underwater"].min()))
        yrs = risk_report["period"]["years"]
        said = {"sell": "you'd likely sell after a 20% fall", "hold": "you'd worry but hold after a 20% fall",
                "buy": "you'd buy more after a 20% fall"}[drop]
        past = ("That's more than 20%, so a drop like your scenario has already happened to this mix." if worst >= 20
                else "That's less than 20%, so your scenario hasn't happened to this mix in that time (it still could).")
        lines.append(f"You said {said}. Over the past {yrs} years this mix's worst fall was <b>{worst:.0f}%</b>. {past}")
    if p.get("decide") == "tips":
        lines.append("You often buy on tips. In <b>Alerts</b>, type why you're buying: the AI coach looks for tip-driven and crowd-driven reasoning.")
    return [l for l in lines if l]


def goal_default() -> str:
    return "low_risk" if profile().get("goal") == "protect" else "sharpe"


def drop_default(fallback: int) -> int:
    return DROP_STARTING_POINT.get(profile().get("drop"), fallback)


def beginner() -> bool:
    return profile().get("experience") == "new" or profile().get("goal") == "learn"
