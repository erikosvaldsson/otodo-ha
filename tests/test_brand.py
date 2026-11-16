"""Brand image tests."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

BRAND_DIR = Path(__file__).parent.parent / "custom_components" / "otodo" / "brand"


async def test_brand_images_are_served(hass: HomeAssistant, hass_client) -> None:
    """Home Assistant serves custom integration icons from <domain>/brand/.

    Without them the integration list and GPM show "icon not available",
    since otodo is not on the central brands CDN.
    """
    assert await async_setup_component(hass, "brands", {})
    client = await hass_client()

    for image in ("icon.png", "logo.png", "dark_icon.png", "icon@2x.png"):
        resp = await client.get(f"/api/brands/integration/otodo/{image}")
        assert resp.status == HTTPStatus.OK, image
        body = await resp.read()
        assert body.startswith(b"\x89PNG"), image
        # Variants we do not ship fall back to the plain icon.
        expected = image if (BRAND_DIR / image).exists() else "icon.png"
        assert body == (BRAND_DIR / expected).read_bytes(), image
