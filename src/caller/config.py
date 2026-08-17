"""Environment configuration with fail-fast validation.

All missing variables are reported in one shot so an operator fixes the env
once, not once per crash. Secrets live only in the gitignored `.env`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

#: The Pretty Good AI assessment line. The dialer refuses any other target so a
#: typo'd env var can never place a test call against a real practice.
TEST_LINE = "+18054398008"

_E164 = re.compile(r"^\+1\d{10}$")


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from_number: str
    target_number: str
    public_base_url: str
    deepgram_api_key: str
    anthropic_api_key: str
    tts_provider: str  # "deepgram" (default) or "elevenlabs"
    default_voice: str
    elevenlabs_api_key: str
    patient_model: str
    judge_model: str
    speculative: bool
    host: str
    port: int


REQUIRED = (
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_FROM_NUMBER",
    "PUBLIC_BASE_URL",
    "DEEPGRAM_API_KEY",
    "ANTHROPIC_API_KEY",
)

#: default patient voice per provider, when neither the scenario nor the env
#: picks one. Deepgram: an Aura-2 voice; ElevenLabs: premade "Rachel".
DEFAULT_VOICES = {"deepgram": "aura-2-thalia-en", "elevenlabs": "21m00Tcm4TlvDq8ikWAM"}


def load_config(env: dict[str, str] | None = None) -> Config:
    e = os.environ if env is None else env

    missing = [k for k in REQUIRED if not e.get(k)]
    if missing:
        raise ConfigError(
            "missing required environment variables: "
            + ", ".join(missing)
            + " (copy .env.example to .env and fill them in)"
        )

    from_number = e["TWILIO_FROM_NUMBER"]
    if not _E164.fullmatch(from_number):
        raise ConfigError(f"TWILIO_FROM_NUMBER must be E.164 (+1XXXXXXXXXX), got {from_number!r}")

    target = e.get("TARGET_NUMBER", TEST_LINE)
    if not _E164.fullmatch(target):
        raise ConfigError(f"TARGET_NUMBER must be E.164 (+1XXXXXXXXXX), got {target!r}")

    base_url = e["PUBLIC_BASE_URL"].rstrip("/")
    if not base_url.startswith("https://"):
        raise ConfigError(f"PUBLIC_BASE_URL must be https (Twilio requires it), got {base_url!r}")

    tts_provider = e.get("TTS_PROVIDER", "deepgram")
    if tts_provider not in DEFAULT_VOICES:
        raise ConfigError(f"TTS_PROVIDER must be one of {sorted(DEFAULT_VOICES)}")
    if tts_provider == "elevenlabs" and not e.get("ELEVENLABS_API_KEY"):
        raise ConfigError("TTS_PROVIDER=elevenlabs requires ELEVENLABS_API_KEY")

    return Config(
        twilio_account_sid=e["TWILIO_ACCOUNT_SID"],
        twilio_auth_token=e["TWILIO_AUTH_TOKEN"],
        twilio_from_number=from_number,
        target_number=target,
        public_base_url=base_url,
        deepgram_api_key=e["DEEPGRAM_API_KEY"],
        anthropic_api_key=e["ANTHROPIC_API_KEY"],
        tts_provider=tts_provider,
        default_voice=e.get("TTS_VOICE") or DEFAULT_VOICES[tts_provider],
        elevenlabs_api_key=e.get("ELEVENLABS_API_KEY", ""),
        patient_model=e.get("PATIENT_MODEL", "claude-haiku-4-5-20251001"),
        judge_model=e.get("JUDGE_MODEL", "claude-sonnet-5"),
        # measured live (call 13): 12/12 speculation hits, zero misses, p50
        # 1.07s with sub-second turns; on by default, SPECULATIVE=0 to disable
        speculative=e.get("SPECULATIVE", "1") == "1",
        host=e.get("HOST", "0.0.0.0"),
        port=int(e.get("PORT", "8765")),
    )


def assert_target_allowed(number: str) -> None:
    """Hard guard: this project only ever dials the assessment line."""
    if number != TEST_LINE and os.environ.get("I_KNOW_WHAT_IM_DOING") != "1":
        raise ConfigError(
            f"refusing to dial {number}: this bot only calls the Pretty Good AI "
            f"test line {TEST_LINE}. (Override requires I_KNOW_WHAT_IM_DOING=1.)"
        )
