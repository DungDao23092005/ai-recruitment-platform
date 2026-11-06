from __future__ import annotations

import re
from typing import Any

from app.schemas.ai_resume import ParsedResumeSchema

REDACTED = "[redacted]"

_EMAIL_KEYS = frozenset(
    {
        "email",
        "emailaddress",
        "contactemail",
        "personalemail",
        "workemail",
        "mail",
    }
)
_PHONE_KEYS = frozenset(
    {
        "phone",
        "phonenumber",
        "mobile",
        "mobilenumber",
        "telephone",
        "contactphone",
        "cell",
        "cellphone",
        "whatsapp",
    }
)
_REDACTED_KEYS = frozenset(
    {
        "address",
        "homeaddress",
        "streetaddress",
        "mailingaddress",
        "physicaladdress",
        "residentialaddress",
        "locationaddress",
        "currentaddress",
        "permanentaddress",
        "linkedin",
        "linkedinurl",
        "linkedinprofile",
        "github",
        "githuburl",
        "githubprofile",
        "gitlab",
        "gitlaburl",
        "website",
        "websiteurl",
        "personalwebsite",
        "personalurl",
        "contacturl",
        "portfoliourl",
        "url",
        "urls",
        "link",
        "links",
        "contact",
        "contacts",
        "contactinfo",
        "contactdetails",
        "social",
        "sociallinks",
        "socialmedia",
        "twitter",
        "x",
        "facebook",
        "instagram",
        "telegram",
        "zalo",
        "skype",
        "discord",
    }
)

_INLINE_EMAIL_RE = re.compile(
    r"(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b"
)
_INLINE_URL_RE = re.compile(
    r"(?i)(?:https?://\S+|mailto:\S+|www\.\S+|\b(?:linkedin\.com|github\.com|gitlab\.com|facebook\.com|twitter\.com|x\.com|instagram\.com|t\.me|zalo\.me)/\S+)"
)
_INLINE_PHONE_RE = re.compile(
    r"(?<!\w)(?:\+\d{1,3}(?:[\s.-]?\d{2,4}){2,4}|\(\d{2,4}\)[\s.-]?\d{3,4}[\s.-]?\d{3,4}|\b0\d{1,3}[\s.-]?\d{3,4}[\s.-]?\d{3,4}|\b\d{3}[\s.-]\d{3}[\s.-]\d{4})(?!\w)"
)


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def _redact_structure(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact_structure(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_structure(item) for item in value]
    return REDACTED


def _scrub_inline_contact_pii(value: str) -> str:
    scrubbed = _INLINE_URL_RE.sub(REDACTED, value)
    scrubbed = _INLINE_EMAIL_RE.sub(REDACTED, scrubbed)
    scrubbed = _INLINE_PHONE_RE.sub(REDACTED, scrubbed)
    return scrubbed


def mask_email(value: str | None) -> str | None:
    if not value:
        return None
    return None


def mask_phone(value: str | None) -> str | None:
    if not value:
        return None
    return None


def mask_contact_value(key: str, value: Any) -> Any:
    normalized = _normalize_key(key)
    if normalized in _EMAIL_KEYS:
        return mask_email(value) if isinstance(value, str) else None
    if normalized in _PHONE_KEYS:
        return mask_phone(value) if isinstance(value, str) else None
    if normalized in _REDACTED_KEYS:
        return _redact_structure(value)
    return mask_pii(value)


def mask_pii(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: mask_contact_value(str(key), item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [mask_pii(item) for item in value]
    if isinstance(value, tuple):
        return [mask_pii(item) for item in value]
    if isinstance(value, str):
        return _scrub_inline_contact_pii(value)
    return value


def mask_parsed_resume(
    parsed_data: dict[str, Any] | None,
) -> ParsedResumeSchema | None:
    if not parsed_data:
        return None
    masked = mask_pii(parsed_data)
    return ParsedResumeSchema.model_validate(masked)
