"""Small logical archive, using MeTube's existing JSON persistence.

Only compact download references are stored. Media and metadata stay in place.
"""
import asyncio
import copy
import hashlib
import json
import math
import os
import time
from types import SimpleNamespace
from urllib.parse import urlsplit

from state_store import AtomicJsonStore
from media_files import media_paths

FIELDS = ('url', 'title', 'filename', 'folder', 'download_type', 'timestamp',
          'size', 'chapter_files', 'subtitle_files')
MAX_METADATA_BYTES = 32 * 1024 * 1024
DEFAULT_CATEGORIES = ['3D Printing', 'Machine and Fab stuff', 'Electronics', 'Funny Stuff']


def text(value):
    return value if isinstance(value, str) else ''


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def source_url(value):
    try:
        return value if urlsplit(text(value)).scheme in ('http', 'https') else ''
    except ValueError:
        return ''


def read_metadata(paths):
    """Read only associated sidecars; never fetch metadata from the internet."""
    warning = ''
    candidates = sorted((p for p in paths if p.endswith('.json')),
                        key=lambda p: not p.endswith('.info.json'))
    metadata = {}
    for path in candidates:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, 'rb') as handle:
                raw = handle.read(MAX_METADATA_BYTES + 1)
            if len(raw) > MAX_METADATA_BYTES:
                warning = 'Some archived metadata is too large to display.'
                continue
            data = json.loads(raw)
            if path.endswith('.comments.json'):
                comments = data if isinstance(data, list) else data.get('comments') if isinstance(data, dict) else None
                if isinstance(comments, list) and 'comments' not in metadata:
                    metadata['comments'] = comments
            elif isinstance(data, dict):
                # Prefer .info.json; a separate comments sidecar may supplement it.
                for key, value in data.items():
                    metadata.setdefault(key, value)
        except (OSError, ValueError):
            warning = 'Some archived metadata could not be read.'
    return metadata, warning


def format_comments(raw):
    if not isinstance(raw, list):
        return []
    result = []
    used = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict) or not text(item.get('text')):
            continue
        key = str(item.get('id') or f'comment-{index}')
        if key in used:
            key = f'{key}-{index}'
        used.add(key)
        parent = item.get('parent')
        result.append({
            'id': key, 'parent': str(parent) if parent not in (None, '', 'root') else None,
            'author': text(item.get('author')) or 'Unknown author',
            'text': item['text'], 'timestamp': number(item.get('timestamp')),
            'time_text': text(item.get('time_text')),
            'likes': number(item.get('like_count')),
            'author_is_uploader': item.get('author_is_uploader') is True,
        })
    return result


class Library:
    def __init__(self, config, queue):
        self.config = config
        self.queue = queue
        self.store = AtomicJsonStore(os.path.join(config.STATE_DIR, 'archive.json'), kind='media_archive')
        payload = self.store.load() or {}
        self.records = payload.get('records', {})
        if not isinstance(self.records, dict):
            raise ValueError('Archive records must be an object')
        self.categories = payload.get('categories', list(DEFAULT_CATEGORIES))
        if not isinstance(self.categories, list) or not all(isinstance(name, str) for name in self.categories):
            raise ValueError('Archive categories must be a list of names')
        self.lock = asyncio.Lock()

    async def _save(self, records, categories):
        await asyncio.to_thread(self.store.save, {'records': records, 'categories': categories})
        self.records = records
        self.categories = categories

    async def create_category(self, name):
        if not isinstance(name, str):
            raise ValueError('Enter a category name.')
        name = ' '.join(name.split())
        if not name or len(name) > 60:
            raise ValueError('Category names must be between 1 and 60 characters.')
        async with self.lock:
            existing = next((item for item in self.categories if item.casefold() == name.casefold()), None)
            if existing:
                return existing
            await self._save(dict(self.records), [*self.categories, name])
            return name

    async def set_categories(self, id, categories):
        if not isinstance(categories, list) or not all(isinstance(name, str) for name in categories):
            raise ValueError('Categories must be a list of names.')
        async with self.lock:
            record = self.get_record(id)
            if any(name not in self.categories for name in categories):
                raise ValueError('One or more categories no longer exist. Refresh and try again.')
            updated = dict(self.records)
            updated[id] = {**record, 'categories': list(dict.fromkeys(categories))}
            await self._save(updated, list(self.categories))

    async def archive(self, id):
        async with self.lock:
            if not self.queue.done.exists(id):
                raise ValueError('This completed download is no longer available.')
            info = self.queue.done.get(id).info
            if getattr(info, 'status', None) != 'finished':
                raise ValueError('Only finished downloads can be archived.')
            record = {field: copy.deepcopy(getattr(info, field, None)) for field in FIELDS}
            record['folder'] = record['folder'] or ''
            paths, _ = await asyncio.to_thread(media_paths, SimpleNamespace(**record), self.config)
            if not os.path.isfile(paths[0]):
                raise ValueError('The downloaded media file is missing.')
            # Stable for a particular local output, including retry after a
            # crash between saving the archive and clearing Completed.
            key = hashlib.sha256(paths[0].encode()).hexdigest()[:24]
            updated = dict(self.records)
            record['archived_at'] = self.records.get(key, {}).get('archived_at', time.time())
            record['categories'] = list(self.records.get(key, {}).get('categories', []))
            updated[key] = record
            await self._save(updated, list(self.categories))
            # Explicit history removal; never call clear(), which can be
            # configured upstream to delete files.
            await self.queue.done.delete(id)
            await self.queue.notifier.cleared(id)
            return key

    def get_record(self, id):
        record = self.records.get(id)
        if not isinstance(record, dict):
            raise KeyError(id)
        return record

    async def delete_media(self, id):
        async with self.lock:
            # Keep the reference until both file cleanup and persistence succeed,
            # so a storage failure can be retried safely.
            await asyncio.to_thread(self._delete_files, id)
            updated = dict(self.records)
            del updated[id]
            await self._save(updated, list(self.categories))

    def _delete_files(self, id):
        paths, _ = self.paths(id)
        if any(os.path.exists(path) and not os.path.isfile(path) for path in paths):
            raise ValueError('An output path is not a regular file')
        for path in paths:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

    def paths(self, id):
        return media_paths(SimpleNamespace(**self.get_record(id)), self.config)

    def item(self, id, details=False):
        record = self.get_record(id)
        warning = ''
        try:
            paths, extensions = self.paths(id)
            metadata, warning = read_metadata(paths)
            available = os.path.isfile(paths[0])
            thumbnail = any(p.lower().endswith(extensions) and os.path.isfile(p) for p in paths)
        except (ValueError, OSError, TypeError):
            metadata, available, thumbnail = {}, False, False
            warning = 'The media path is unavailable.'
        title = text(metadata.get('title')) or text(record.get('title')) or 'Untitled video'
        creator = text(metadata.get('uploader')) or text(metadata.get('creator')) or text(metadata.get('channel'))
        timestamp = number(record.get('timestamp'))
        result = {
            'id': id, 'title': title, 'creator': creator,
            'description': text(metadata.get('description')),
            'downloaded_at': timestamp / 1_000_000 if timestamp is not None else None,
            'source': source_url(metadata.get('webpage_url')) or source_url(record.get('url')),
            'available': available, 'thumbnail': thumbnail,
            'download_type': text(record.get('download_type')),
            'warning': warning,
            'categories': record.get('categories', []),
        }
        if details:
            result['comments'] = format_comments(metadata.get('comments'))
        return result

    def list_items(self):
        return sorted((self.item(id) for id in list(self.records)),
                      key=lambda item: item['downloaded_at'] or 0, reverse=True)
