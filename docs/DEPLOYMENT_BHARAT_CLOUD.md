# Deploying the Migration Tool to Bharat Cloud (aaPanel)

Same VM as the vendor management app and CRM (aaPanel + Docker already installed),
managed the same way: push-to-deploy via GitHub Actions over SSH. Single environment —
production only, one port.

| Environment | Branch | Directory on VM                        | Port |
|-------------|--------|------------------------------------------|------|
| Production  | `main` | `~/apps/migration-tool-production`       | 8050 |

**Architecture**: one `app` container — FastAPI serves the built React frontend
directly (no separate frontend container, no CORS at runtime) — plus a `db` container
(Postgres). `db` is **not** published to the host, matching vendor/CRM's choice of never
exposing the database to the internet.

---

## 1. Open the port

The VM already has aaPanel, Docker, and the deploy key set up (from the vendor/CRM
deployments), so this is the only new step. Two places need it open, or traffic won't
get through even if one of them allows it:

- **Bharat Cloud's firewall/security-group console** (TCP, inbound): **8050**,
  alongside whatever's already open for vendor and CRM.
- **aaPanel's own firewall**: Security → Firewall → Add Port Rule → 8050 (TCP).

## 2. Postgres

This app's `db` container is **not** published to the host at all (no `ports:` entry in
docker-compose.yml), so it can't collide with vendor's or CRM's own Postgres containers
— each app's database is a fully separate container/volume, even though they all run on
the same Docker host. If you ever need to reach this app's database directly (e.g.
`psql`), do it via `docker compose exec db psql -U migrationtool -d migrationtool` from
inside the checkout directory, or uncomment the loopback-only `ports:` line in
docker-compose.yml and tunnel through SSH the same way described in the CRM deployment
doc, rather than exposing a host port.

## 3. Deploy key

If the vendor/CRM deploy key is already on this VM and you're fine reusing it for this
repo too, skip straight to step 4 — just reuse the same `SSH_PRIVATE_KEY` value in this
repo's GitHub Actions secrets. Otherwise, add a key the same one-time way:

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "<your github-actions-deploy public key>" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

That's it for the VM side — **the workflow bootstraps everything else itself**: cloning
the repo into `~/apps/migration-tool-production` on its first run, and writing `.env`
from GitHub secrets if it isn't there yet. Nothing left to clone or configure by hand.

---

## 4. GitHub repo setup

In this repo: **Settings → Secrets and variables → Actions → New repository secret**,
add:

- `SSH_HOST` — the VM's IP address (same VM as vendor/CRM)
- `SSH_USER` — the VM user the deploy key is set up for
- `SSH_PRIVATE_KEY` — full contents of the private key file (the whole
  `-----BEGIN...-----`/`-----END...-----` block)
- `SSH_PORT` — only if SSH runs on something other than 22
- `PROD_DB_PASSWORD` — generate with `openssl rand -base64 24`

Push to `main` → GitHub Actions SSHes in, clones the repo into
`~/apps/migration-tool-production` if it's not there yet, writes `.env` from
`PROD_DB_PASSWORD` if one doesn't exist yet, then builds and starts the stack on port
8050. Also runnable on-demand from the Actions tab (`workflow_dispatch`) without a new
commit — useful for the very first deploy.

Confirm it worked:
```bash
curl http://<VM_IP>:8050/api/health   # should return {"status":"ok"}
curl http://<VM_IP>:8050/             # the app itself
```

**The database starts empty** — no projects, no uploaded files. Just open
`http://<VM_IP>:8050` and create the first project through the UI.

### See it in aaPanel

Once it's deployed at least once: Docker plugin → Compose (or "Container Manage" /
"Compose Manage") → Import, pointing at
`~/apps/migration-tool-production/docker-compose.yml`. This just gives you a UI over the
same containers/logs/restart controls — it doesn't change how it got deployed.

---

## 5. Large file uploads on this VM

This app is built around multi-million-row CSV uploads (customer master files, etc.) —
noticeably heavier than vendor's KYC documents or CRM's typical attachments. Two things
worth checking on this VM before a first real upload:

- **Disk space** — uploaded CSVs, their Parquet copies, and validation result files all
  live in the `migrationtool_storage` Docker volume. A single 1M+ row source file plus
  its Parquet copy can be a few hundred MB to low GB; budget accordingly alongside
  vendor/CRM's own volumes on the same disk.
- **Reverse proxy body-size limits** — if you later put this behind aaPanel's Website /
  reverse-proxy feature (step 6), aaPanel's underlying nginx has a default
  `client_max_body_size` that will reject large uploads with a 413 unless raised. Not an
  issue hitting `http://<VM_IP>:8050` directly (no proxy in front), only once a domain +
  reverse proxy is added.

---

## 6. Later: domain via aaPanel

When you have a domain, aaPanel's Website manager does the reverse proxy + SSL work
you'd otherwise hand-write in nginx:

1. Website → Add Site, for `migration.yourcompany.in`, no PHP/static root needed.
2. On that site, add a **Reverse Proxy** rule → target `http://127.0.0.1:8050`.
3. Config tab → raise `client_max_body_size` (e.g. `2048m`) so large CSV uploads aren't
   rejected by the proxy — see the note above.
4. SSL tab → Let's Encrypt → issue a free cert for it. aaPanel handles renewal.

No changes to the app or containers needed for any of this.
