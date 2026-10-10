"""Stand-ins shared by the orchestration tests: a scripted orchestrator and fake agents. No model, web or
knowledge-layer call is made."""
from app.orchestration.agents import StepContext
from app.orchestration.orchestrator import Decision, Scope

FEEDBACK, TREND, CLUSTERING = "Customer Feedback Agent", "Market & Trend Agent", "Clustering Agent"
FILE, LOCATOR = "G60_feedback_hackathon.xlsx", "sheet Feedback_Explorer, row 12"


def call(agent, reason=None):
    return Decision("call", agent, reason or f"because {agent}")


FINISH = Decision("finish")


class ScriptedOrchestrator:
    """Answers `decide` from a list (then finishes) and records what it was shown each time."""

    def __init__(self, *decisions, scope=Scope("A title", "G60", "US"), scope_error=None):
        self.decisions, self._scope, self.scope_error, self.calls, self.seen_requests = list(decisions), scope, scope_error, [], []

    def scope(self, request):
        self.seen_requests.append(request)
        if self.scope_error:
            raise self.scope_error
        return self._scope

    def decide(self, request, scope, history, notes, calls_left):
        self.calls.append({"history": list(history), "notes": list(notes), "calls_left": calls_left})
        decision = self.decisions.pop(0) if self.decisions else FINISH
        if isinstance(decision, BaseException):
            raise decision
        return decision


def finding(text="Seat ventilation is too weak.", locator=LOCATOR):
    return {"text": text, "signal_type": "complaint", "evidence_level": "Verified", "source_file": FILE,
            "locator": locator, "market": "US", "vehicle_line": "G60", "assumptions": [], "out_of_scope_reason": None}


def cited(agent, *findings):
    bullets = "\n".join(f"- {f['text']} ({FILE}, {f['locator']})" for f in findings) or "- No findings."
    return {"agent_name": agent, "vehicle_line": "G60", "market": "US", "findings": list(findings),
            "summary": f"{agent} looked at the G60 / US feedback.\n\nFindings:\n{bullets}"}


class FakeAgent:
    """Records every context it is called with and answers from a list (the last answer repeats)."""

    def __init__(self, name, *answers):
        self.name, self.answers, self.seen = name, list(answers) or [cited(name, finding())], []

    def __call__(self, ctx: StepContext):
        self.seen.append(ctx)
        answer = self.answers[min(len(self.seen), len(self.answers)) - 1]
        if isinstance(answer, BaseException):
            raise answer
        return answer
