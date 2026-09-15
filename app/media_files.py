"""File association for the fork UI; does not participate in downloading."""
import json
import os
from ytdl import _is_within_directory


def media_paths(info, config):
    root = os.path.realpath(config.AUDIO_DOWNLOAD_DIR if info.download_type == 'audio' else config.DOWNLOAD_DIR)
    folder = getattr(info, 'folder', '') or ''
    directory = os.path.abspath(os.path.join(root, folder))
    if (os.path.isabs(folder) or not _is_within_directory(root, os.path.realpath(directory))
            or directory != os.path.realpath(directory)
            or not isinstance(getattr(info, 'filename', None), str) or not info.filename):
        raise ValueError('No safe downloaded media path is available')
    base = os.path.realpath(directory)
    names = [info.filename]
    for field in ('chapter_files', 'subtitle_files'):
        names.extend(item['filename'] for item in (getattr(info, field, None) or [])
                     if isinstance(item, dict) and item.get('filename'))
    images = ('.jpg', '.jpeg', '.png', '.webp', '.avif')
    suffixes = images + ('.info.json', '.json', '.comments.json', '.description')
    for name in list(names):
        stem = os.path.splitext(name)[0]
        names.extend(stem + suffix for suffix in suffixes)
    # Older yt-dlp filename trimming can leave an extra dotted suffix on
    # the media but not the info JSON. Only accept this exact alternative
    # when its embedded source URL confirms the association.
    stem = os.path.splitext(info.filename)[0]
    legacy = os.path.splitext(stem)[0] + '.info.json'
    legacy_path = os.path.join(base, legacy)
    if (legacy not in names and not os.path.islink(legacy_path)
            and _is_within_directory(base, os.path.realpath(legacy_path))
            and os.path.isfile(legacy_path)):
        try:
            if os.path.getsize(legacy_path) <= 16 * 1024 * 1024:
                with open(legacy_path, encoding='utf-8') as metadata_file:
                    metadata = json.load(metadata_file)
                if (isinstance(metadata, dict) and getattr(info, 'url', None)
                        and metadata.get('webpage_url') == info.url):
                    names.append(legacy)
        except (OSError, ValueError):
            pass
    paths = []
    for name in dict.fromkeys(names):
        path = os.path.join(base, name)
        resolved = os.path.realpath(path)
        if (os.path.isabs(name) or not _is_within_directory(base, resolved)
                or _is_within_directory(os.path.realpath(config.STATE_DIR), resolved)
                or '.metube' in name.replace('\\', '/').split('/')
                or os.path.islink(path) or resolved != os.path.abspath(path)):
            raise ValueError('Unsafe media path; no files were deleted')
        paths.append(path)
    return paths, images
