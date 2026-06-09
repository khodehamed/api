# Seven Hub 3x-ui API bridge

Flask app for checking, rotating, and temporarily toggling VLESS/Shadowsocks
clients across multiple MHSanaei/3x-ui panels.

The UI template is kept inline in `app.py`. The backend supports both:

- New 3x-ui client API: `/panel/api/clients/...`
- Legacy inbound client API: `/panel/api/inbounds/updateClient/:clientId`

## Install

```bash
python3 -m pip install -r requirements.txt
```

## Required configuration

Do not hard-code panel passwords in the source. Set either a shared password:

```bash
export XUI_PANEL_USERNAME='hamex'
export XUI_PANEL_PASSWORD='your-panel-password'
export CHANGE_SECTION_PASSWORD='your-change-tab-password'
```

Or use API token authentication for supported 3x-ui versions:

```bash
export XUI_PANEL_TOKEN='your-3x-ui-api-token'
```

Per-panel overrides are also supported. Example:

```bash
export XUI_LINKW_GOZAR8_IR_PASSWORD='panel-specific-password'
export XUI_LINKW_GOZAR8_IR_TOKEN='panel-specific-token'
```

You can replace the built-in panel list completely with `PANELS_JSON`:

```bash
export PANELS_JSON='{
  "example.com": {
    "url": "https://1.2.3.4:2096/panel-path",
    "domain": "example.com",
    "username": "admin",
    "password": "secret"
  }
}'
```

## Run

```bash
sudo -E python3 app.py
```

Set `PORT` if you do not want to bind to port 80:

```bash
PORT=8080 python3 app.py
```