# BKW Smart Meter – Home Assistant Integration

Unofficial Home Assistant custom integration that reads **grid consumption** from the [BKW customer portal](https://my.bkw.ch/) (daily totals), using the same APIs as the web app.

## Features

- OAuth2 login (open BKW in the browser, paste the authorization code into Home Assistant)
- Automatic access-token refresh
- Configurable polling every **1–10** minutes (default **10**)
- Sensors:
  - **Consumption (latest day)** – kWh for the latest published portal day
  - **Consumption total** – cumulative kWh for the Energy dashboard

## Limitations

BKW only provides **complete past calendar days**, not live “today so far” usage. During the day you typically see **yesterday’s** total (Swiss time, `Europe/Zurich`). After **midnight Swiss**, the next finished day appears once BKW publishes it.

There is no 15-minute or hourly data in the portal API today, so the integration is best for **daily history** and the **Energy dashboard**, not real-time load tracking.

## Requirements

- Home Assistant **2024.6.0** or newer
- BKW account with smart-meter data on [my.bkw.ch](https://my.bkw.ch/)

## Installation

### Option A: Copy to `custom_components`

1. Copy `custom_components/bkw_smartmeter` into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. **Settings → Devices & services → Add integration** → **BKW Smart Meter**.

### Option B: HACS

1. HACS → **Integrations** → **Custom repositories** → add  
   `https://github.com/pavax/home-assistant-bkw-smartmeter` (category **Integration**).
2. Install **BKW Smart Meter**, restart Home Assistant, then add the integration as above.
3. Install updates from the HACS **BKW Smart Meter** update entry when available.

## Configuration

### Log in

1. Start the config flow and open the **authorize URL** in a browser.
2. Log in to BKW.
3. After redirect to `https://my.bkw.ch/energy?code=...`, copy only the **`code`** value from the URL.
4. Paste the code into Home Assistant.

Codes expire quickly; if login fails, start the flow again.

### Metering point code

Enter your **metering point code**, e.g. `CH1022201234500000000000000196130`.

To find it:

1. Open [my.bkw.ch/energy](https://my.bkw.ch/energy) and the **Strombezug** chart.
2. Browser **DevTools → Network**, filter `metering-data`.
3. Copy `meteringPointCode` from the request URL.

### Data type

For most meters, **Strombezug** (grid import) uses `PRODUCTION_BKW` (the default). Other charts may need `CONSUMPTION_BKW` or another value from your portal.

| Portal chart | `dataType` |
|--------------|------------|
| **Strombezug** (grid import) | `PRODUCTION_BKW` |
| Other (e.g. feed-in) | Often `CONSUMPTION_BKW` — check your portal |

If setup returns a 400 error, copy the `dataType` from a working `metering-data` request in DevTools and set it under **Configure → Options**.

### Update interval

**Configure → Options → Update interval (minutes)** (1–10). Use at most **10** minutes so tokens are refreshed before BKW’s ~15 minute session timeout. Changes apply immediately without a restart.

## Energy dashboard

**Settings → Dashboards → Energy** → add **Grid consumption** → select **Consumption total**.

## Re-authentication

If sensors stop updating or Home Assistant asks to reauthenticate:

1. Open the integration → **Reconfigure** (or remove and add it again).
2. Repeat the login steps above.

## Security and disclaimer

- Unofficial integration; BKW may change APIs without notice.
- Tokens stay in your Home Assistant config entry only.
- Do not share captures or logs that contain tokens.
- Use at your own risk; comply with [BKW terms of use](https://www.bkw.ch/).

## Development

Smoke-test in Docker from the repository root:

```bash
./scripts/verify-docker.sh
```

Details: `scripts/bkw-smartmeter-ha-verify/docker-compose.yml`.
