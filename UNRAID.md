# Running on Unraid (from your own GHCR build)

This fork's GitHub Actions workflow (`.github/workflows/docker-build.yml`)
builds the image and pushes it to GitHub Container Registry on every push to
`main` — no Docker Hub account or self-hosted runner needed.

## 1. Push to your fork and let CI build the image

```bash
git remote set-url origin https://github.com/<you>/pick-a-recipe.git   # if not already pointed at your fork
git push origin main
```

Watch it run under the repo's **Actions** tab. When it finishes, the image is
available at:

```
ghcr.io/<you>/pick-a-recipe:latest
```

(GitHub lowercases the owner/repo automatically, so it doesn't matter what
case your username or repo name use.)

## 2. Make the package pullable from Unraid

Newly published GHCR packages are **private** by default. Pick one:

- **Public (simplest for personal testing):** on GitHub, go to
  `https://github.com/<you>?tab=packages` → open the `pick-a-recipe` package →
  **Package settings** → **Change visibility** → **Public**. After that,
  Unraid can pull it with no login.
- **Keep it private:** in Unraid, go to **Docker tab → Registrations** (or
  run on the host terminal):
  ```bash
  docker login ghcr.io -u <you>
  # password: a GitHub Personal Access Token (classic) with the read:packages scope
  ```

## 3. Add the container via Unraid's Docker manager (GUI)

### Option A — Import the template XML (fastest)

[`unraid-template.xml`](unraid-template.xml) is a standard Unraid Docker
container template you can register locally:

1. Edit the two `REPLACE_WITH_YOUR_GITHUB_USERNAME` placeholders in the file
   (repository image path, support link, icon URL) to match your fork.
2. Copy it onto the Unraid box at
   `/boot/config/plugins/dockerMan/templates-user/pick-a-recipe.xml`
   (e.g. `scp unraid-template.xml root@<unraid-ip>:/boot/config/plugins/dockerMan/templates-user/pick-a-recipe.xml`).
3. In the Unraid UI: **Docker tab → Add Container**, then pick
   **pick-a-recipe** from the **Template** dropdown at the top. All fields
   (port, paths, env vars) are pre-filled — just set `FLASK_SECRET_KEY` to a
   random value (e.g. output of `openssl rand -hex 32`) and click **Apply**.

### Option B — Fill in Add Container by hand

If you'd rather not import the template, **Docker tab → Add Container** and
fill in:

| Field | Value |
|---|---|
| Name | `pick-a-recipe` |
| Repository | `ghcr.io/<you>/pick-a-recipe:latest` |
| Network Type | `bridge` |
| Port: Container `5006` → Host | `5006` (or any free port) |
| Path: Container `/app/data` → Host | `/mnt/user/appdata/pick-a-recipe` |
| Path: Container `/tmp` → Host | `/mnt/user/appdata/pick-a-recipe/tmp` |
| Variable: `FLASK_SECRET_KEY` | a random secret, e.g. output of `openssl rand -hex 32` |
| Variable: `MAX_CONCURRENT_JOBS` (optional) | `3` |

Apply, then open `http://<unraid-ip>:5006` and log in with `admin` /
`admin123` (change it immediately — see the main README).

## 4. Getting new builds

Every push to `main` overwrites the `:latest` tag on GHCR. To pick up a new
build in Unraid: **Docker tab → pick-a-recipe → Force Update**.

## Leftover files from the original author's setup

`docker-compose.yml`, `docker-compose.srv2.yml`, `portainer/`,
`build-and-push.sh`, and `scripts/portainer-deploy.sh` are specific to the
upstream project's own Docker Hub account and home Portainer server — they
aren't wired into this fork's CI anymore and can be deleted if you don't need
them as reference.
