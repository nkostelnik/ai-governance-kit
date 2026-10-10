import os

from ai_governance.llm import load_env_file


def test_env_file_is_read_without_overriding_real_env(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# comment\nAIGOV_TEST_A="from-file"\nAIGOV_TEST_B=from-file\n', encoding="utf-8")
    monkeypatch.delenv("AIGOV_TEST_A", raising=False)
    monkeypatch.setenv("AIGOV_TEST_B", "from-real-env")
    load_env_file(env)
    assert os.environ["AIGOV_TEST_A"] == "from-file"
    assert os.environ["AIGOV_TEST_B"] == "from-real-env"
    monkeypatch.delenv("AIGOV_TEST_A")


def test_blank_value_is_not_loaded(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("AIGOV_TEST_C=\n", encoding="utf-8")
    monkeypatch.delenv("AIGOV_TEST_C", raising=False)
    load_env_file(env)
    assert "AIGOV_TEST_C" not in os.environ


def test_missing_env_file_is_fine(tmp_path):
    load_env_file(tmp_path / "nope.env")


def test_cost_counts_cached_tokens():
    from ai_governance.llm import LLMResult
    r = LLMResult(parsed=None, stop_reason="end_turn", input_tokens=1000, cache_write_tokens=4000,
                  cache_read_tokens=0, output_tokens=1000)
    assert round(r.cost_usd(), 4) == round((1000 + 5000) * 2 / 1e6 + 1000 * 10 / 1e6, 4)
