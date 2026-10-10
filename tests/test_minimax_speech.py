import json

import httpx

from app.clients.minimax_speech import MiniMaxSpeechClient
from app.config import Settings


def test_minimax_speech_decodes_hex_audio() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer key"
        payload = json.loads(request.content)
        assert payload["model"] == "speech-2.8-hd"
        return httpx.Response(
            200,
            json={"base_resp": {"status_code": 0}, "data": {"audio": "000102"}, "extra_info": {"audio_length": 1000}},
        )

    transport = httpx.MockTransport(handler)
    client = MiniMaxSpeechClient(
        Settings(_env_file=None, MINIMAX_API_KEY="key"),
        client=httpx.Client(transport=transport),
    )
    result = client.synthesize(text="旁白", voice_id="male-qn-qingse")
    assert result.audio_bytes == b"\x00\x01\x02"
    assert result.reported_duration_seconds == 1.0

