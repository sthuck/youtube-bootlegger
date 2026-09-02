"""Declarative description of every user-editable application setting.

Both UIs drive their settings forms from this table instead of repeating a
read/write/notify block per field. Adding a setting means adding one
``SettingField`` here plus the matching property on :class:`AppSettings`.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..core.settings import AppSettings, LlmProvider


def _snake_to_camel(name: str) -> str:
    """Convert a snake_case settings attribute to a camelCase QML name."""
    head, *rest = name.split("_")
    return head + "".join(part.title() for part in rest)


def _coerce_llm_provider(value: Any) -> LlmProvider:
    """Normalize any provider input to a supported LlmProvider member."""
    try:
        provider = LlmProvider(value)
    except ValueError:
        return LlmProvider.CHATGPT_LITE
    if provider == LlmProvider.NONE:
        return LlmProvider.CHATGPT_LITE
    return provider


def _read_llm_provider(settings: AppSettings) -> str:
    """Read the active provider as its plain string value."""
    return settings.llm_provider.value


@dataclass(frozen=True)
class SettingField:
    """One user-editable setting and how the UIs should surface it.

    Attributes:
        name: Attribute name on :class:`AppSettings`.
        value_type: Python type exposed to QML (``str`` or ``bool``).
        secret: True for credentials, so forms can mask the input.
        affects_llm_config: Changing it may flip whether an LLM is usable.
        affects_ffmpeg: Changing it may flip whether ffmpeg is available.
        coerce: Optional normalizer applied before writing.
        read: Optional reader used instead of plain attribute access.
    """

    name: str
    value_type: type
    secret: bool = False
    affects_llm_config: bool = False
    affects_ffmpeg: bool = False
    coerce: Callable[[Any], Any] | None = None
    read: Callable[[AppSettings], Any] | None = None

    @property
    def qml_name(self) -> str:
        """camelCase property name exposed to QML."""
        return _snake_to_camel(self.name)

    @property
    def signal_name(self) -> str:
        """Notify-signal name for the QML property."""
        return f"{self.qml_name}Changed"

    @property
    def slot_name(self) -> str:
        """Invokable setter name exposed to QML."""
        camel = self.qml_name
        return f"set{camel[0].upper()}{camel[1:]}"

    def read_from(self, settings: AppSettings) -> Any:
        """Return this field's current value from ``settings``."""
        if self.read is not None:
            return self.read(settings)
        return getattr(settings, self.name)

    def write_to(self, settings: AppSettings, value: Any) -> None:
        """Write ``value`` to ``settings``, applying any coercion first."""
        setattr(settings, self.name, self.coerce(value) if self.coerce else value)


SETTING_FIELDS: tuple[SettingField, ...] = (
    SettingField("use_external_ytdlp", bool),
    SettingField("ytdlp_path", str),
    SettingField("ffmpeg_path", str, affects_ffmpeg=True),
    SettingField(
        "llm_provider",
        str,
        affects_llm_config=True,
        coerce=_coerce_llm_provider,
        read=_read_llm_provider,
    ),
    SettingField("openai_api_key", str, secret=True, affects_llm_config=True),
    SettingField("openai_model", str),
    SettingField("anthropic_api_key", str, secret=True, affects_llm_config=True),
    SettingField("anthropic_model", str),
    SettingField("vertex_api_key", str, secret=True, affects_llm_config=True),
    SettingField("vertex_model", str),
    SettingField("compatible_base_url", str, affects_llm_config=True),
    SettingField("compatible_bearer_token", str, secret=True),
    SettingField("compatible_model", str),
)

SETTING_FIELDS_BY_NAME: dict[str, SettingField] = {
    field.name: field for field in SETTING_FIELDS
}
