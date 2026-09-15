import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from library import Library, format_comments
from library_routes import register_library


@pytest.fixture
def environment(tmp_path):
    config = SimpleNamespace(DOWNLOAD_DIR=str(tmp_path), AUDIO_DOWNLOAD_DIR=str(tmp_path),
                             STATE_DIR=str(tmp_path / '.metube'), URL_PREFIX='/')
    info = SimpleNamespace(url='https://example.com/video', title='Full original title',
                           filename='video.mp4', download_type='video', folder='',
                           status='finished', timestamp=1_700_000_000_000_000_000,
                           size=5)
    records = {'completed': SimpleNamespace(info=info)}

    async def delete(id):
        records.pop(id, None)

    queue = SimpleNamespace(done=SimpleNamespace(exists=lambda id: id in records,
                            get=lambda id: records[id], delete=AsyncMock(side_effect=delete)),
                            notifier=SimpleNamespace(cleared=AsyncMock()))
    (tmp_path / 'video.mp4').write_bytes(b'video')
    (tmp_path / 'video.jpg').write_bytes(b'thumbnail')
    (tmp_path / 'video.info.json').write_text(json.dumps({
        'title': 'one two three four five six seven eight hidden searchable words',
        'uploader': 'Original Creator', 'description': 'A searchable description',
        'webpage_url': info.url,
        'comments': [{'id': 'a', 'author': 'Alice', 'text': 'Hello', 'like_count': 3},
                     {'id': 'b', 'author': 'Bob', 'text': '<script>text only</script>', 'parent': 'a'}],
    }))
    return config, queue, records, tmp_path


@pytest.mark.asyncio
async def test_archive_persists_without_moving_or_changing_any_media(environment):
    config, queue, records, root = environment
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir() if p.is_file()}
    library = Library(config, queue)
    key = await library.archive('completed')
    assert not records
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir() if p.is_file()}
    reloaded = Library(config, queue)
    item = reloaded.item(key, True)
    assert item['creator'] == 'Original Creator'
    assert item['title'].endswith('hidden searchable words')
    assert item['description'] == 'A searchable description'
    assert item['comments'][1]['parent'] == 'a'
    assert item['comments'][1]['text'] == '<script>text only</script>'
    assert item['downloaded_at'] == 1_700_000_000_000
    stored = json.loads(Path(reloaded.store.path).read_text())
    assert 'comments' not in stored['records'][key]
    assert 'description' not in stored['records'][key]


@pytest.mark.asyncio
async def test_failed_archive_write_keeps_completed(environment):
    config, queue, records, root = environment
    library = Library(config, queue)
    with patch.object(library.store, 'save', side_effect=OSError('full disk')):
        with pytest.raises(OSError):
            await library.archive('completed')
    assert 'completed' in records
    assert not library.records
    assert (root / 'video.mp4').exists()


@pytest.mark.asyncio
async def test_retry_after_history_write_failure_does_not_duplicate_archive(environment):
    config, queue, records, _ = environment
    library = Library(config, queue)
    original_delete = queue.done.delete
    queue.done.delete = AsyncMock(side_effect=OSError('history save failed'))
    with pytest.raises(OSError):
        await library.archive('completed')
    assert 'completed' in records
    assert len(Library(config, queue).records) == 1
    queue.done.delete = original_delete
    await library.archive('completed')
    assert len(library.records) == 1
    assert not records


@pytest.mark.asyncio
async def test_missing_metadata_and_missing_media_degrade_gracefully(environment):
    config, queue, _, root = environment
    library = Library(config, queue)
    key = await library.archive('completed')
    (root / 'video.info.json').unlink()
    assert library.item(key, True)['comments'] == []
    assert library.item(key)['title'] == 'Full original title'
    (root / 'video.mp4').unlink()
    assert library.item(key)['available'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('filename', ['../outside.mp4', '.metube/archive.json'])
async def test_archive_rejects_unsafe_paths(environment, filename):
    config, queue, records, _ = environment
    records['completed'].info.filename = filename
    with pytest.raises(ValueError):
        await Library(config, queue).archive('completed')
    assert 'completed' in records


@pytest.mark.asyncio
async def test_corrupt_metadata_is_reported_without_breaking_archive(environment):
    config, queue, _, root = environment
    (root / 'video.info.json').write_text('{broken')
    library = Library(config, queue)
    key = await library.archive('completed')
    assert library.item(key, True)['warning']
    assert library.item(key, True)['comments'] == []


def test_comment_fields_are_optional_and_nonfinite_values_are_ignored():
    result = format_comments([None, {'text': 'Hi', 'timestamp': float('nan')},
                              {'text': 'Reply', 'id': 5, 'parent': 4, 'like_count': 0}])
    assert len(result) == 2
    assert result[0]['author'] == 'Unknown author'
    assert result[0]['timestamp'] is None
    assert result[1]['parent'] == '4'
    assert result[1]['likes'] == 0


@pytest.mark.asyncio
async def test_archive_http_media_range_thumbnail_and_reload(environment):
    config, queue, _, _ = environment
    routes = web.RouteTableDef()

    async def read_json(request):
        return await request.json()

    register_library(routes, config, queue, SimpleNamespace(emit=AsyncMock()), read_json, lambda post: post['id'])
    app = web.Application()
    app.add_routes(routes)
    async with TestClient(TestServer(app)) as client:
        response = await client.post('/library/archive', json={'id': 'completed'})
        assert response.status == 200
        key = (await response.json())['id']
        response = await client.get('/library')
        assert (await response.json())[0]['id'] == key
        response = await client.get(f'/library/{key}')
        assert len((await response.json())['comments']) == 2
        response = await client.get(f'/library/{key}/media', headers={'Range': 'bytes=0-1'})
        assert response.status == 206
        assert await response.read() == b'vi'
        response = await client.get(f'/library/{key}/thumbnail')
        assert response.status == 200
        assert response.content_type == 'image/jpeg'
        response = await client.get('/library/missing/media')
        assert response.status == 404
