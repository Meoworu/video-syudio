import base64
from pathlib import Path

import httpx

from app.clients.google_omni_video import GoogleOmniVideoClient
from app.config import Settings


class FakeInteractions:
    def __init__(self) -> None:
        self.created = []

    def create(self, **kwargs):
        self.created.append(kwargs)
        return {"id": "interaction-1"}

    def get(self, **kwargs):
        return {"status": "completed", "steps": [{"content": [{"type": "video", "data": base64.b64encode(b"mp4").decode()}]}]}


class FakeClient:
    def __init__(self) -> None:
        self.interactions = FakeInteractions()


def test_google_omni_submits_both_frames_and_saves_inline_video(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    last = tmp_path / "last.png"
    first.write_bytes(b"first")
    last.write_bytes(b"last")
    fake = FakeClient()
    client = GoogleOmniVideoClient(Settings(_env_file=None, GOOGLE_CLOUD_PROJECT="project"), client=fake)
    job_id = client.create_interaction(
        prompt="slow camera move",
        first_frame=first,
        last_frame=last,
        aspect_ratio="9:16",
        duration_seconds=5,
    )
    assert job_id == "interaction-1"
    assert len(fake.interactions.created[0]["input"]) == 3
    output = tmp_path / "video.mp4"
    client.save_video(client.wait_for_completion(job_id), output)
    assert output.read_bytes() == b"mp4"

