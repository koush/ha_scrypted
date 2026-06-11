"""Bridge between Home Assistant's WebRTC client sessions and Scrypted signaling.

Home Assistant's camera WebRTC model: the frontend creates an SDP offer and
expects an answer plus trickled ICE candidates over a message callback.

Scrypted's model: a device implementing RTCSignalingChannel is handed an
RTCSignalingSession peer and drives the negotiation itself (mirroring
@scrypted/common's connectRTCSignalingClients with the client as offerer):

1. camera calls our createLocalDescription("offer", setup, sendIceCandidate)
   -> we return HA's offer and keep sendIceCandidate for HA->camera trickle
2. camera calls our setRemoteDescription(answer) -> forwarded to HA
3. camera calls our addIceCandidate(candidate) -> forwarded to HA
"""
from __future__ import annotations

import logging
from typing import Any

from webrtc_models import RTCIceCandidateInit

from homeassistant.components.camera import (
    WebRTCAnswer,
    WebRTCCandidate,
    WebRTCSendMessage,
)

_LOGGER = logging.getLogger(__name__)


class HomeAssistantSignalingSession:
    """A scrypted RTCSignalingSession backed by a HA WebRTC client session."""

    def __init__(self, offer_sdp: str, send_message: WebRTCSendMessage) -> None:
        self.offer_sdp = offer_sdp
        self.send_message = send_message
        self.control: Any = None
        self._send_ice_candidate: Any = None
        self._pending_client_candidates: list[dict[str, Any]] = []
        self.options: dict[str, Any] = {"userAgent": "home-assistant"}
        # rpc.py ships these to the remote peer as readable proxy properties.
        self.__dict__["__proxy_props"] = {"options": self.options}

    # -- RTCSignalingSession interface (called by the scrypted camera) --

    async def getOptions(self) -> dict[str, Any]:  # noqa: N802 - scrypted API
        return self.options

    async def createLocalDescription(  # noqa: N802 - scrypted API
        self, type: str, setup: dict, sendIceCandidate: Any = None  # noqa: N803
    ) -> dict[str, str]:
        if type != "offer":
            raise ValueError(
                "Home Assistant always provides the offer; the scrypted peer "
                f"asked for a local {type}"
            )
        self._send_ice_candidate = sendIceCandidate
        if sendIceCandidate:
            while self._pending_client_candidates:
                await sendIceCandidate(self._pending_client_candidates.pop(0))
        return {"type": "offer", "sdp": self.offer_sdp}

    async def setRemoteDescription(  # noqa: N802 - scrypted API
        self, description: dict, setup: dict
    ) -> None:
        if (description or {}).get("type") == "answer":
            self.send_message(WebRTCAnswer(answer=description["sdp"]))

    async def addIceCandidate(self, candidate: dict) -> None:  # noqa: N802
        self.send_message(
            WebRTCCandidate(
                candidate=RTCIceCandidateInit(
                    candidate.get("candidate"),
                    sdp_mid=candidate.get("sdpMid"),
                    sdp_m_line_index=candidate.get("sdpMLineIndex"),
                )
            )
        )

    # -- HA side --

    async def add_client_candidate(self, candidate: RTCIceCandidateInit) -> None:
        """Trickle a HA frontend candidate to the scrypted peer.

        Candidates may arrive before the camera has requested the offer (and
        with it handed us its sendIceCandidate callback); buffer until then.
        """
        payload = {
            "candidate": candidate.candidate,
            "sdpMid": candidate.sdp_mid,
            "sdpMLineIndex": candidate.sdp_m_line_index,
        }
        if self._send_ice_candidate:
            await self._send_ice_candidate(payload)
        else:
            self._pending_client_candidates.append(payload)

    async def async_end(self) -> None:
        """End the scrypted-side session."""
        if self.control:
            try:
                await self.control.endSession()
            except Exception:  # noqa: BLE001 - best effort teardown
                _LOGGER.debug("Error ending scrypted RTC session", exc_info=True)
            self.control = None
