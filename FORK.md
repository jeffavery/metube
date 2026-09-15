# Jeff's MeTube fork

Upstream: https://github.com/alexta69/metube (remote `upstream`).
Fork: https://github.com/jeffavery/metube (remote `origin`).
Deployment branch: `completed-media`; upstream `master` stays clean.
Source: `/opt/docker/metube/source`; deployment: `/opt/docker/metube/compose.yml`.

## Local changes

- Separate confirmed Delete Media action; existing trash/history behavior is unchanged.
- Delete the recorded primary, chapter and subtitle outputs and exact-stem JPG/JPEG/PNG/WebP/AVIF, JSON/info JSON/comments JSON and description sidecars. Missing files are tolerated; unsafe paths and storage failures retain history for retry.
- Older dotted filename trimming: accept the alternative info JSON only when its embedded source URL matches the record. No broad prefix deletion or folder scans.
- Serve local thumbnails beside Completed titles, linking to the media. Hide missing thumbnails.
- Display the first eight words plus an ellipsis only for longer Completed titles. Metadata and filename generation are unchanged.

Files removed from history before this fork cannot be managed from Completed. Nonstandard sidecar names are deliberately not guessed.

## Update

Keep `/opt/docker/metube/compose.yml` and NAS runtime data outside Git.
From the source folder, fetch upstream and merge `upstream/master` into `completed-media`.
Review conflicts, run the checks in AGENTS.md, then build:

```sh
docker build --build-arg TARGETARCH=amd64 --build-arg VERSION=jeffavery-archive -t jeffavery/metube:archive .
```

Save the current image and compose file before rebuilding/deploying. Deploy from `/opt/docker/metube` with `docker compose up -d --no-deps metube`. Keep the NAS mount, port and all environment settings unchanged. Verify container health and the Completed page, then push the branch.

Initial rollback: `/opt/docker/metube/rollback-20260915` contains the original compose file and MeTube state archive; `metube:rollback-20260915` preserves the original running image. To roll back application code, set the compose image to that tag and recreate MeTube. Do not restore the state archive over newer history unless deliberately recovering state.

## Archive and Play pages

The Archive action is logical only. It saves a compact reference in
`STATE_DIR/archive.json` using the existing `AtomicJsonStore`, then removes the
Completed record without touching any downloaded files. Save failure keeps the
Completed record; retry after a partial state write is idempotent. The existing
NAS mount and deployment settings are unchanged. No database service is added.

Implementation lives in `app/library.py`, `app/library_routes.py` and
`ui/src/app/library/`. File association from the earlier fork now lives in
`app/media_files.py`, shared by Completed and Archive. No yt-dlp extraction or
core download behavior is changed. Explicit UI history clears bypass the optional
upstream file-deletion setting.

Archive search uses full title, creator, description and source. The Play page
reads local media with HTTP range support and renders optional saved comments as
text with authors, dates, likes and reply grouping. It does not fetch remote
metadata or comments. Metadata is read from associated JSON files on demand, with
a 32 MiB per-file limit and a visible warning for unreadable/oversized metadata.
The index does not duplicate full metadata or comments. Missing media remains
listed as unavailable. Files already cleared from Completed are not imported
automatically. Existing downloads are not automatically archived on deployment.

Save Comments is a one-submission checkbox above Advanced Options, using the
existing server preset named `Save Comments`. It starts off, is excluded from
saved form presets and subscription/batch defaults, and resets upon submission.
Availability and completeness of comments remain platform-dependent.

Verification: frontend lint/build and tests; backend persistence, failure recovery,
path protections, metadata fallbacks and HTTP range tests; isolated browser test
with synthetic video and threaded comments, search beyond the displayed title,
playback and archive persistence after container restart.

Archive rollout rollback: `/opt/docker/metube/rollback-archive-20260915` stores
the previous compose and state. `metube:pre-archive-20260915` preserves the previous
live image. To revert the UI, use that image and recreate the service while keeping
current NAS state. The archive index can remain on disk for a future re-upgrade.


Archive rows include a separate confirmed Delete Media action. It removes the
associated local media and sidecars before removing the archive reference.
Storage/persistence errors keep the reference for retry; missing files are tolerated.
The feature uses the same guarded file resolver as Completed. No downloader changes.
