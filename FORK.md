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
docker build --build-arg TARGETARCH=amd64 --build-arg VERSION=jeffavery-completed-media -t jeffavery/metube:completed-media .
```

Save the current image and compose file before rebuilding/deploying. Deploy from `/opt/docker/metube` with `docker compose up -d --no-deps metube`. Keep the NAS mount, port and all environment settings unchanged. Verify container health and the Completed page, then push the branch.

Initial rollback: `/opt/docker/metube/rollback-20260915` contains the original compose file and MeTube state archive; `metube:rollback-20260915` preserves the original running image. To roll back application code, set the compose image to that tag and recreate MeTube. Do not restore the state archive over newer history unless deliberately recovering state.
