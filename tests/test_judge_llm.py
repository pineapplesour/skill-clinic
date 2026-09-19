"""Offline tests for the Nosana LLM judge: no network, no GPU job, stubbed client."""

import types

import openai

from clinic.judge import classify, classify_with_llm


class _StubClient:
    """Minimal stand-in for openai.OpenAI that replays one canned reply."""

    reply = ""
    seen: dict = {}

    def __init__(self, **kwargs):
        _StubClient.seen = kwargs
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        _StubClient.seen.update(kwargs)
        message = types.SimpleNamespace(content=_StubClient.reply)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


def _stub(monkeypatch, reply: str, model: str = "qwen3.5:9b"):
    _StubClient.reply = reply
    monkeypatch.setattr(openai, "OpenAI", _StubClient)
    monkeypatch.setenv("LLM_BASE_URL", "https://job.node.k8s.prd.nos.ci/v1")
    monkeypatch.setenv("LLM_MODEL", model)
    monkeypatch.setenv("LLM_API_KEY", "x")


def test_strict_json_is_parsed_out_of_a_fenced_prose_reply(monkeypatch):
    _stub(monkeypatch, 'Sure! Here is my analysis:\n```json\n'
                       '{"category": "stale_command", "explanation": "flag was removed",\n'
                       ' "fix_command": "`pip install daytona`", "confidence": 0.91}\n'
                       '```\nHope that helps.')
    v = classify_with_llm("pip install --use-feature=2020-resolver daytona",
                          "no such option: --use-feature", 1)
    assert v["category"] == "stale_command"
    assert v["explanation"] == "flag was removed"
    assert v["fix_command"] == "pip install daytona"   # backticks stripped
    assert v["confidence"] == 0.91
    assert v["judge"].startswith("nosana:")
    assert v["judge"] == "nosana:qwen3.5:9b"
    assert _StubClient.seen["base_url"] == "https://job.node.k8s.prd.nos.ci/v1"
    assert _StubClient.seen["model"] == "qwen3.5:9b"


def test_out_of_vocabulary_category_is_clamped_to_unknown(monkeypatch):
    _stub(monkeypatch, '{"category": "Cosmic Rays", "explanation": "who knows",'
                       ' "fix_command": null, "confidence": 5}')
    v = classify_with_llm("python app.py", "boom", 1)
    assert v["category"] == "unknown"
    assert v["fix_command"] is None
    assert v["confidence"] == 1.0   # clamped into [0, 1]
    assert v["judge"].startswith("nosana:")


def test_missing_secret_fix_is_suppressed_even_if_the_model_invents_one(monkeypatch):
    _stub(monkeypatch, '{"category": "missing_secret", "explanation": "needs a key",'
                       ' "fix_command": "export DAYTONA_API_KEY=sk-guessed", "confidence": 0.8}')
    v = classify_with_llm("python -c ...", "Set the DAYTONA_API_KEY environment variable", 1)
    assert v["category"] == "missing_secret"
    assert v["fix_command"] is None   # we never invent a credential
    assert v["judge"].startswith("nosana:")


def test_unparseable_reply_falls_back_to_rules_and_reports_it(monkeypatch):
    _stub(monkeypatch, "I am afraid I cannot do that.")
    seen = []
    v = classify("daytona sandbox create --name demo", "bash: daytona: command not found",
                 1, use_llm=True, on_fallback=seen.append)
    assert v["judge"] == "rules"
    assert v["category"] == "stale_command"
    assert len(seen) == 1   # the fallback is never silent
