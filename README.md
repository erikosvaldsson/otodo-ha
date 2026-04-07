# otodo-ha

Home Assistant custom integration for [otodo](https://gitlab.com/erik.osvaldsson/otodo) — a web-based todo and project management app.

Each otodo project appears as a separate todo list entity in Home Assistant.

## Features

- List, create, update, and delete todo items
- Edit todo text from within Home Assistant
- Each project is a separate todo list entity

## Installation

### HACS (recommended)

1. Open HACS in your Home Assistant instance
2. Click the three-dot menu in the top right and select **Custom repositories**
3. Add this repository URL with category **Integration**
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
| URL | Base URL of your otodo instance (e.g. `http://192.168.1.100:8080`) |
| API Key | Bearer token from the otodo admin panel |
