"""Internal error hierarchy for FUBON fetcher flow.

These errors live inside the FUBON module and are caught at the fetcher
boundary (``FubonFetcher.fetch_pdf``) and remapped to the project-wide
``FetchError`` contract. Keeping them internal lets the flow/client code
raise with rich context without leaking the internal state machine into
the pipeline error surface.
"""

from __future__ import annotations


class FubonFlowError(Exception):
    """Base class for FUBON internal flow errors."""


class FubonRedirectError(FubonFlowError):
    """Raised when a redirect points outside the FUBON domain allowlist."""


class FubonSessionError(FubonFlowError):
    """Raised when SPA session state is invalid (cookies, captcha payload)."""


class FubonLoginError(FubonFlowError):
    """Raised when ``doLogin`` returns a non-success code.

    ``code`` is the normalised reason slug: ``captcha_wrong``, ``id_wrong``,
    ``birthday_wrong``, ``record_not_found``, or ``unknown``.
    """

    def __init__(
        self,
        code: str,
        raw_code: int | None = None,
        message: str = "",
    ) -> None:
        super().__init__(
            f"fubon doLogin failed: code={code} raw={raw_code} msg={message}"
        )
        self.code = code
        self.raw_code = raw_code
        self.raw_message = message
