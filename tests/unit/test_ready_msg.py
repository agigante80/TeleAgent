"""Unit tests for src/ready_msg.py."""
from unittest.mock import MagicMock, patch

from src.ready_msg import ai_label, build_ready_message, _resolve_sha
from src.config import Settings, AIConfig, BotConfig, GitHubConfig, DirectAIConfig


def _make_settings(cli="api", provider="openai", model="gpt-4o", image_tag="", git_sha=""):
    s = MagicMock(spec=Settings)
    ai = MagicMock(spec=AIConfig)
    ai.ai_cli = cli
    ai.ai_model = model
    direct = MagicMock(spec=DirectAIConfig)
    direct.ai_provider = provider
    ai.direct = direct
    bot = MagicMock(spec=BotConfig)
    bot.image_tag = image_tag
    bot.git_sha = git_sha
    gh = MagicMock(spec=GitHubConfig)
    gh.github_repo = "owner/repo"
    gh.branch = "main"
    s.ai = ai
    s.bot = bot
    s.github = gh
    return s


class TestAiLabel:
    def test_api_with_provider_and_model(self):
        s = _make_settings(cli="api", provider="openai", model="gpt-4o")
        assert ai_label(s) == "api/openai (gpt-4o)"

    def test_non_api_cli_uses_cli_name(self):
        s = _make_settings(cli="copilot", provider="", model="")
        assert ai_label(s) == "copilot"

    def test_non_api_cli_with_model(self):
        s = _make_settings(cli="codex", provider="", model="o3")
        assert ai_label(s) == "codex (o3)"

    def test_api_without_provider(self):
        s = _make_settings(cli="api", provider="", model="")
        assert ai_label(s) == "api"


class TestBuildReadyMessage:
    def test_basic_message_contains_key_fields(self):
        s = _make_settings(image_tag="")
        msg = build_ready_message(s, "1.0.0", "gate")
        assert "AgentGate Ready" in msg
        assert "v1.0.0" in msg
        assert "owner/repo" in msg
        assert "/gate help" in msg

    def test_image_tag_included_when_set(self):
        s = _make_settings(image_tag="latest")
        msg = build_ready_message(s, "1.2.3", "gate")
        assert ":latest" in msg
        assert "v1.2.3" in msg

    def test_no_tag_when_image_tag_empty(self):
        s = _make_settings(image_tag="")
        msg = build_ready_message(s, "1.2.3", "gate")
        assert "`:latest`" not in msg
        assert "`:develop`" not in msg


class TestResolveSha:
    def test_returns_git_sha_from_settings_when_set(self):
        s = _make_settings(git_sha="f907318")
        assert _resolve_sha(s) == "f907318"

    def test_calls_git_when_settings_sha_empty(self):
        s = _make_settings(git_sha="")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc1234\n"
        with patch("src.ready_msg.subprocess.run", return_value=mock_result) as mock_run:
            sha = _resolve_sha(s)
        assert sha == "abc1234"
        mock_run.assert_called_once()

    def test_returns_empty_on_git_failure(self):
        s = _make_settings(git_sha="")
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("src.ready_msg.subprocess.run", return_value=mock_result):
            sha = _resolve_sha(s)
        assert sha == ""

    def test_returns_empty_on_exception(self):
        s = _make_settings(git_sha="")
        with patch("src.ready_msg.subprocess.run", side_effect=OSError("not found")):
            sha = _resolve_sha(s)
        assert sha == ""


class TestBuildReadyMessageGitSha:
    """Acceptance criteria from the feature spec."""

    def test_image_tag_latest_no_sha_shown(self):
        # AC1: IMAGE_TAG=latest → no SHA, production format
        s = _make_settings(image_tag="latest", git_sha="f907318")
        msg = build_ready_message(s, "0.17.0", "gate")
        assert "v0.17.0 `:latest`" in msg
        assert "dev" not in msg

    def test_image_tag_empty_no_sha_shown(self):
        # AC2: IMAGE_TAG="" → no SHA, bare version
        s = _make_settings(image_tag="", git_sha="f907318")
        msg = build_ready_message(s, "0.17.0", "gate")
        assert "v0.17.0" in msg
        assert "dev" not in msg
        assert "f907318" not in msg

    def test_dev_tag_with_explicit_sha(self):
        # AC3: IMAGE_TAG=local-dev, GIT_SHA=f907318 → v{ver}-dev-f907318
        s = _make_settings(image_tag="local-dev", git_sha="f907318")
        msg = build_ready_message(s, "0.17.0", "gate")
        assert "v0.17.0-dev-f907318" in msg

    def test_dev_tag_git_resolves_sha(self):
        # AC4: IMAGE_TAG=develop, no GIT_SHA, git returns sha → v{ver}-dev-{sha}
        s = _make_settings(image_tag="develop", git_sha="")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc1234\n"
        with patch("src.ready_msg.subprocess.run", return_value=mock_result):
            msg = build_ready_message(s, "0.17.0", "gate")
        assert "v0.17.0-dev-abc1234" in msg

    def test_dev_tag_git_fails_fallback_format(self):
        # AC5: IMAGE_TAG=local-dev, no GIT_SHA, git fails → fallback v{ver} :local-dev
        s = _make_settings(image_tag="local-dev", git_sha="")
        with patch("src.ready_msg.subprocess.run", side_effect=OSError("git not found")):
            msg = build_ready_message(s, "0.17.0", "gate")
        assert "v0.17.0 `:local-dev`" in msg
        assert "dev-" not in msg
