import pytest

from app.sync import processor


@pytest.mark.asyncio
async def test_deleted_or_inactive_datasource_is_terminal_not_retryable(monkeypatch):
    async def resolve_deleted(_job):
        raise processor.SyncJobTerminalError("datasource ds-1 is inactive")

    monkeypatch.setattr(processor, "_process_once", resolve_deleted)

    result = await processor.process_sync({"store_id": "store-1", "datasource_id": "ds-1"})

    assert result.errors == ["datasource ds-1 is inactive"]
    assert result.data_quality["terminal"] == "datasource_inactive_or_deleted"
    assert "retry" not in result.data_quality