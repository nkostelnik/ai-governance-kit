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


def test_missing_env_file_is_fine(tmp_path):
    load_env_file(tmp_path / "nope.env")
