from __future__ import annotations

import io
import unicodedata
import uuid

from PIL import Image, ImageOps, UnidentifiedImageError

from app.domain.models import AssetImage, Project, ProjectAsset, Shot
from app.store.project_store import ProjectStore


MAX_IMAGE_BYTES = 6_000_000
MAX_IMAGE_PIXELS = 40_000_000


class InvalidImageError(ValueError):
    pass


def normalize_image(content: bytes, content_type: str) -> tuple[bytes, int, int]:
    if content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise InvalidImageError("只支持 PNG、JPG 或 WebP 图片")
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise InvalidImageError("图片不能为空且不能超过 6 MB")
    try:
        with Image.open(io.BytesIO(content)) as source:
            if source.format not in {"PNG", "JPEG", "WEBP"} or getattr(source, "n_frames", 1) != 1:
                raise InvalidImageError("图片格式不支持或包含动画")
            expected_type = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[source.format]
            if content_type != expected_type:
                raise InvalidImageError("图片内容与文件类型不匹配")
            width, height = source.size
            if width * height > MAX_IMAGE_PIXELS:
                raise InvalidImageError("图片分辨率不能超过 40 MP")
            source.load()
            image = ImageOps.exif_transpose(source)
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            output = io.BytesIO()
            image.save(output, format="WEBP", quality=92, method=4)
            quality = 84
            while output.tell() > MAX_IMAGE_BYTES and quality >= 60:
                output = io.BytesIO()
                image.save(output, format="WEBP", quality=quality, method=4)
                quality -= 8
            while output.tell() > MAX_IMAGE_BYTES and max(image.size) > 512:
                image.thumbnail((int(image.width * 0.8), int(image.height * 0.8)), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                image.save(output, format="WEBP", quality=76, method=4)
            if output.tell() > MAX_IMAGE_BYTES:
                raise InvalidImageError("图片无法压缩到模型支持的大小")
            return output.getvalue(), image.width, image.height
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise InvalidImageError("无法读取图片，请上传有效的 PNG、JPG 或 WebP") from error


def resolve_asset_references(project: Project, shot: Shot, mode: str = "auto", asset_ids: list[str] | None = None) -> tuple[list[ProjectAsset], list[str]]:
    if mode == "manual":
        selected = set(asset_ids or [])
        assets = [asset for asset in project.assets if asset.id in selected and asset.image]
        if len(assets) != len(selected):
            raise ValueError("所选参考资产不存在或尚未上传图片")
        return assets, []

    names = {normalize_name(name) for name in shot.visibleCharacters}
    if shot.locationName.strip():
        names.add(normalize_name(shot.locationName))
    matched = [
        asset for asset in project.assets
        if asset.kind in {"character", "location"} and normalize_name(asset.entityName or asset.name) in names
    ]
    missing = [asset.name for asset in matched if not asset.image]
    references = [asset for asset in matched if asset.image]
    references.extend(
        asset for asset in project.assets
        if asset.kind == "reference" and shot.id in asset.scopeShotIds and asset.image
    )
    return references, missing


def normalize_name(name: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", name).split()).casefold()


def attach_asset_image(store: ProjectStore, project_id: str, asset: ProjectAsset, content: bytes, content_type: str) -> None:
    normalized, width, height = normalize_image(content, content_type)
    save_asset_image(store, project_id, asset, normalized, width, height)


def save_asset_image(store: ProjectStore, project_id: str, asset: ProjectAsset, content: bytes, width: int, height: int) -> None:
    image_id = uuid.uuid4().hex
    path = f"assets/{asset.id}/{image_id}.webp"
    store.save_media(project_id, path, content)
    asset.image = AssetImage(imageId=image_id, path=path, mimeType="image/webp", size=len(content), width=width, height=height)
    asset.revision += 1
