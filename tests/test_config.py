"""Config validation: aggregate errors, E.164 checks, the dial guard."""

import pytest

from caller.config import TEST_LINE, ConfigError, assert_target_allowed, load_config

GOOD_ENV = {
    "TWILIO_ACCOUNT_SID": "AC123",
    "TWILIO_AUTH_TOKEN": "tok",
    "TWILIO_FROM_NUMBER": "+16265551234",
    "PUBLIC_BASE_URL": "https://abc.ngrok.app/",
    "DEEPGRAM_API_KEY": "dg",
    "ANTHROPIC_API_KEY": "an",
    "ELEVENLABS_API_KEY": "el",
}


class TestLoadConfig:
    def test_happy_path_defaults(self):
        cfg = load_config(GOOD_ENV)
        assert cfg.target_number == TEST_LINE
        assert cfg.public_base_url == "https://abc.ngrok.app"  # trailing slash stripped
        assert cfg.patient_model.startswith("claude-haiku")
        assert cfg.elevenlabs_voice_id  # falls back to the default voice

    def test_all_missing_vars_reported_at_once(self):
        dropped = ("DEEPGRAM_API_KEY", "ANTHROPIC_API_KEY")
        env = {k: v for k, v in GOOD_ENV.items() if k not in dropped}
        with pytest.raises(ConfigError) as e:
            load_config(env)
        assert "DEEPGRAM_API_KEY" in str(e.value)
        assert "ANTHROPIC_API_KEY" in str(e.value)

    def test_bad_from_number(self):
        with pytest.raises(ConfigError, match="E.164"):
            load_config({**GOOD_ENV, "TWILIO_FROM_NUMBER": "626-555-1234"})

    def test_http_base_url_rejected(self):
        with pytest.raises(ConfigError, match="https"):
            load_config({**GOOD_ENV, "PUBLIC_BASE_URL": "http://abc.ngrok.app"})


class TestDialGuard:
    def test_test_line_allowed(self):
        assert_target_allowed(TEST_LINE)

    def test_other_numbers_refused(self, monkeypatch):
        monkeypatch.delenv("I_KNOW_WHAT_IM_DOING", raising=False)
        with pytest.raises(ConfigError, match="refusing to dial"):
            assert_target_allowed("+13105551234")
