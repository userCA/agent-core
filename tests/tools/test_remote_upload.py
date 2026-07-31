"""Tests for Migu remote upload helper."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from agent_core.tools.remote_upload import upload_bytes_to_remote


@pytest.mark.asyncio
@respx.mock
async def test_upload_bytes_success() -> None:
    route = respx.post("http://upload.musicapp.nf.migu.cn/file/upload/v1.1").mock(
        return_value=Response(
            200,
            json={"code": "000000", "data": [{"url": "https://cdn.example.com/a.png"}]},
        )
    )
    url = await upload_bytes_to_remote(
        data=b"fake-png",
        filename="a.png",
        content_type="image/png",
    )
    assert url == "https://cdn.example.com/a.png"
    assert route.called
    req = route.calls.last.request
    assert req.headers.get("sid")
    assert b"serviceType" in req.content or "serviceType" in str(req.content)


@pytest.mark.asyncio
@respx.mock
async def test_upload_bytes_business_error() -> None:
    respx.post("http://upload.musicapp.nf.migu.cn/file/upload/v1.1").mock(
        return_value=Response(
            200,
            json={"code": "100001", "message": "bad file", "data": []},
        )
    )
    with pytest.raises(RuntimeError, match="远端上传失败"):
        await upload_bytes_to_remote(data=b"x", filename="x.png")


@pytest.mark.asyncio
@respx.mock
async def test_save_and_remote_upload(tmp_path, monkeypatch) -> None:
    from scene.common.upload_handler import save_and_remote_upload

    respx.post("http://upload.musicapp.nf.migu.cn/file/upload/v1.1").mock(
        return_value=Response(
            200,
            json={"code": "000000", "data": [{"url": "https://cdn.example.com/b.jpg"}]},
        )
    )
    result = await save_and_remote_upload(
        raw=b"jpeg-bytes",
        filename="b.jpg",
        cwd=str(tmp_path),
        content_type="image/jpeg",
    )
    assert result["success"] is True
    assert result["url"] == "https://cdn.example.com/b.jpg"
    assert result["path"].startswith(".pi/uploads/")
    assert (tmp_path / result["path"]).is_file()
