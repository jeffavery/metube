"""Archive HTTP integration, isolated from upstream download handlers."""
import asyncio
import os
from aiohttp import web
from library import Library


def register_library(routes, config, queue, sio, read_json, require_id):
    library = Library(config, queue)
    prefix = config.URL_PREFIX + 'library'

    @routes.post(prefix + '/archive')
    async def archive(request):
        post = await read_json(request)
        try:
            id = await library.archive(require_id(post))
        except ValueError as error:
            return web.json_response({'status': 'error', 'msg': str(error)}, status=400)
        except OSError:
            return web.json_response({'status': 'error', 'msg': 'Archive could not be saved completely. Retry; media files were not changed.'}, status=500)
        await sio.emit('library_changed', {})
        return web.json_response({'status': 'ok', 'id': id})

    @routes.get(prefix)
    async def listing(request):
        return web.json_response(await asyncio.to_thread(library.list_items))

    @routes.get(prefix + '/{id}')
    async def details(request):
        try:
            return web.json_response(await asyncio.to_thread(library.item, request.match_info['id'], True))
        except KeyError:
            raise web.HTTPNotFound()

    @routes.get(prefix + '/{id}/media')
    async def media(request):
        try:
            paths, _ = await asyncio.to_thread(library.paths, request.match_info['id'])
            path = paths[0]
            if not os.path.isfile(path):
                raise web.HTTPNotFound()
            return web.FileResponse(path)
        except (KeyError, ValueError, OSError):
            raise web.HTTPNotFound()

    @routes.get(prefix + '/{id}/thumbnail')
    async def thumbnail(request):
        try:
            paths, extensions = await asyncio.to_thread(library.paths, request.match_info['id'])
            path = next((p for p in paths if p.lower().endswith(extensions) and os.path.isfile(p)), None)
            if not path:
                raise web.HTTPNotFound()
            return web.FileResponse(path, headers={'Cache-Control': 'no-cache'})
        except (KeyError, ValueError, OSError):
            raise web.HTTPNotFound()

    return library
