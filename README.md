# otodo-ha

Home Assistant custom integration for [otodo](https://gitlab.com/erik.osvaldsson/otodo) — a web-based todo and project management app.

Each otodo project appears as a separate todo list entity in Home Assistant.

## Features

- List, create, update, and delete todo items
- Edit todo text from within Home Assistant
- Each project is a separate todo list entity; projects created later appear automatically
- Live updates pushed from otodo, with polling as a fallback
- HTTPS, including otodo's self-signed certificate (pinned by fingerprint)

Requires Home Assistant 2025.3 or newer.

## Installation

### GPM (recommended)

1. Install [GPM](https://github.com/Greip-code/gpm) if you haven't already
2. Run `gpm install gitlab.com/erik.osvaldsson/otodo-ha`
3. Restart Home Assistant
4. Go to **Settings > Devices & Services > Add Integration** and search for **otodo**
5. Enter your otodo instance URL and an API key (create one from the otodo admin panel at `/admin`)

### HACS

1. Open HACS in Home Assistant
2. Click the three-dot menu in the top right and select **Custom repositories**
3. Add `https://github.com/erikosvaldsson/otodo-ha` as a repository with category **Integration**
4. Search for **otodo** in HACS and install it
5. Restart Home Assistant
6. Go to **Settings > Devices & Services > Add Integration** and search for **otodo**
7. Enter your otodo instance URL and an API key (create one from the otodo admin panel at `/admin`)

### Manual

1. Copy the `custom_components/otodo` folder into your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant
3. Go to **Settings > Devices & Services > Add Integration** and search for **otodo**
4. Enter your otodo instance URL and an API key (create one from the otodo admin panel at `/admin`)

## Configuration

| Field | Description |
|-------|-------------|
| URL | Base URL of your otodo instance, e.g. `https://otodo.example.com` or `https://192.168.1.100:8080` |
| API key | Bearer token from the otodo admin panel |
| Verify SSL certificate | On by default. Turn off to accept a self-signed certificate without checking it |
| Certificate fingerprint | Optional. Trust exactly this certificate (see below). Overrides *Verify SSL certificate* |

To change any of these later, open the integration in **Settings > Devices & Services** and
choose **Reconfigure**. Entities and their history are kept. If otodo rejects the API key,
Home Assistant asks for a new one.

### Connecting to otodo's self-signed certificate

When otodo runs with `TLS_CERT`/`TLS_KEY` and generates its own certificate, browsers and
Home Assistant cannot verify it. If Home Assistant reaches otodo through a reverse proxy
with a real certificate, use that URL and nothing changes. To connect directly instead:

1. Copy the fingerprint otodo logs at startup:
   ```
   TLS certificate SHA-256 fingerprint: 59:63:9A:D0:...
   ```
   (or run `openssl x509 -in cert.pem -noout -fingerprint -sha256`).
2. Set the URL to `https://<host>:<port>` and paste the fingerprint into **Certificate fingerprint**.

Home Assistant then trusts exactly that certificate. If it is ever regenerated, update the
fingerprint via **Reconfigure**.

If an existing setup used an `http://` URL and otodo has since switched to HTTPS, the
integration stops loading and logs *"otodo is serving HTTPS; change the URL to https://"*.
Fix it with **Reconfigure** as above.

## Development

```bash
pip install -r requirements_test.txt
pytest
ruff check .
```

The tests run against the current Home Assistant release, including TLS checks against a
real local HTTPS server.
