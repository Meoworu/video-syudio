import base64
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.clients.google_omni_video import GoogleOmniVideoClient, GoogleOmniVideoError
from app.config import Settings


class FakeInteractions:
    def __init__(self) -> None:
        self.created = []

    def create(self, **kwargs):
        self.created.append(kwargs)
        return {"id": "interaction-1"}

    def get(self, **kwargs):
        return {"status": "completed", "steps": [{"content": [{"type": "video", "data": base64.b64encode(b"mp4").decode()}]}]}

    def cancel(self, *args, **kwargs):
        return {"status": "cancelled"}


class FakeFiles:
    def __init__(self):
        self.downloaded = []

    def get(self, *, name):
        assert name == "files/video-123"
        return {"state": "ACTIVE"}

    def download(self, *, file, destination):
        self.downloaded.append(file)
        destination.write(b"mp4")


class FakeClient:
    def __init__(self) -> None:
        self.interactions = FakeInteractions()
        self.files = FakeFiles()


def test_google_omni_submits_both_frames_and_saves_inline_video(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.clients.google_omni_video.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"streams": [{"codec_type": "video"}], "format": {"duration": "5"}}),
            stderr="",
        ),
    )
    first = tmp_path / "first.png"
    last = tmp_path / "last.png"
    first.write_bytes(b"first")
    last.write_bytes(b"last")
    fake = FakeClient()
    client = GoogleOmniVideoClient(Settings(_env_file=None), client=fake)
    job_id = client.create_interaction(
        prompt="slow camera move",
        first_frame=first,
        last_frame=last,
        aspect_ratio="9:16",
        duration_seconds=5,
    )
    assert job_id == "interaction-1"
    request = fake.interactions.created[0]
    assert len(request["input"]) == 3
    assert request["input"][0]["type"] == "image"
    assert "label" not in request["input"][0]
    assert request["input"][2]["type"] == "text"
    assert "FIRST_FRAME" in request["input"][2]["text"]
    assert request["response_format"] == {"type": "video", "aspect_ratio": "9:16"}
    assert "duration" not in request["response_format"]
    assert "background" not in request["input"][2]
    output = tmp_path / "video.mp4"
    client.save_video(client.wait_for_completion(job_id), output)
    assert output.read_bytes() == b"mp4"


def test_google_omni_downloads_gemini_file_uri_through_files_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.clients.google_omni_video.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"streams": [{"codec_type": "video"}], "format": {"duration": "5"}}),
            stderr="",
        ),
    )
    fake = FakeClient()
    client = GoogleOmniVideoClient(Settings(_env_file=None), client=fake)
    output = tmp_path / "video.mp4"
    interaction = {"status": "completed", "steps": [{"content": [{
        "type": "video", "uri": "https://generativelanguage.googleapis.com/v1beta/files/video-123:download?alt=media"
    }]}]}

    client.save_video(interaction, output)

    assert output.read_bytes() == b"mp4"
    assert fake.files.downloaded == ["https://generativelanguage.googleapis.com/v1beta/files/video-123:download?alt=media"]


def test_google_omni_rejects_non_google_file_uri(tmp_path: Path) -> None:
    client = GoogleOmniVideoClient(Settings(_env_file=None), client=FakeClient())
    interaction = {"status": "completed", "steps": [{"content": [{"type": "video", "uri": "https://example.com/files/video-123"}]}]}

    with pytest.raises(GoogleOmniVideoError, match="URI 无效"):
        client.save_video(interaction, tmp_path / "video.mp4")
    assert not (tmp_path / "video.mp4").exists()

