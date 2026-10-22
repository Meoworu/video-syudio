import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.clients.google_omni_video import GoogleOmniVideoCancelled, GoogleOmniVideoClient, GoogleOmniVideoError, _gemini_file_name
from app.config import Settings


class FakeInteractions:
    def __init__(self) -> None:
        self.created = []

    def create(self, **kwargs):
        self.created.append(kwargs)
        return {"id": "interaction-1"}

    def get(self, **kwargs):
        return {"status": "completed", "output_video": {"type": "video", "data": base64.b64encode(b"mp4").decode()}}

    def cancel(self, *args, **kwargs):
        return {"status": "cancelled"}


class FakeClient:
    def __init__(self) -> None:
        self.interactions = FakeInteractions()
        self.files = None


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
    assert request["response_format"] == {"type": "video", "aspect_ratio": "9:16", "delivery": "uri", "duration": "5s"}
    assert "background" not in request["input"][2]
    output = tmp_path / "video.mp4"
    client.save_video(client.wait_for_completion(job_id), output)
    assert output.read_bytes() == b"mp4"


@pytest.mark.parametrize("uri", [
    "https://example.com/files/video-123",
    "https://generativelanguage.googleapis.com/v1beta/files/video-123:download?alt=media",
    "https://user@generativelanguage.googleapis.com/v1beta/files/video-123",
    "gs://bucket/video.mp4",
])
def test_google_omni_rejects_unsafe_uri_output(tmp_path: Path, uri: str) -> None:
    client = GoogleOmniVideoClient(Settings(_env_file=None), client=FakeClient())
    interaction = {"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "video", "uri": uri}]}]}
    output = tmp_path / "video.mp4"
    with pytest.raises(GoogleOmniVideoError, match="不受支持的视频文件地址"):
        client.save_video(interaction, output)
    assert not output.exists()
    assert not output.with_name("video.part.mp4").exists()


def test_gemini_files_uri_is_validated_and_downloaded(tmp_path: Path, monkeypatch) -> None:
    class FakeFiles:
        def __init__(self):
            self.states = iter(["PROCESSING", "ACTIVE"])
            self.lookups = []
            self.downloads = []

        def get(self, *, name):
            self.lookups.append(name)
            return {"name": name, "state": next(self.states)}

        def download(self, *, file, destination):
            self.downloads.append((file["name"], destination))
            Path(destination).write_bytes(b"downloaded-mp4")

    fake = FakeClient()
    fake.files = FakeFiles()
    client = GoogleOmniVideoClient(Settings(_env_file=None, GOOGLE_VIDEO_API_KEY="video-key", GOOGLE_POLL_INTERVAL_SECONDS=0.001), client=fake)
    monkeypatch.setattr(
        "app.clients.google_omni_video.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"streams": [{"codec_type": "video"}], "format": {"duration": "5"}}),
            stderr="",
        ),
    )
    uri = "https://generativelanguage.googleapis.com/v1beta/files/video-123"
    assert _gemini_file_name(uri) == "files/video-123"
    output = tmp_path / "video.mp4"
    client.save_video({"status": "completed", "output_video": {"type": "video", "uri": uri}}, output)
    assert fake.files.lookups == ["files/video-123", "files/video-123"]
    assert fake.files.downloads[0][0] == "files/video-123"
    assert output.read_bytes() == b"downloaded-mp4"


def test_google_omni_cancels_inline_write_and_removes_partial(tmp_path: Path) -> None:
    output = tmp_path / "video.mp4"
    checks = 0

    def cancel_check():
        nonlocal checks
        checks += 1
        return checks >= 2

    client = GoogleOmniVideoClient(Settings(_env_file=None), client=FakeClient())
    interaction = {"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "video", "data": base64.b64encode(b"x" * (3 * 1024 * 1024)).decode()}]}]}
    with pytest.raises(GoogleOmniVideoCancelled):
        client.save_video(interaction, output, cancel_check=cancel_check)
    assert not output.exists()
    assert not output.with_name("video.part.mp4").exists()
