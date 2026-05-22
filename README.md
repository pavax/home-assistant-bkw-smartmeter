# BKW Smart Meter – Home Assistant Integration

Unofficial Home Assistant custom integration for customers of **[BKW](https://www.bkw.ch/)** (*Berner Kantonalwerke*), the electricity utility for Bern and much of Switzerland.

If you have one of BKW’s **new smart meters**, your daily energy data is available in the **[myBKW](https://my.bkw.ch/)** customer portal (website and app). This integration logs in like the portal, reads the same **daily kWh** values (e.g. **Strombezug** / grid import), and exposes them as Home Assistant sensors — including support for the **Energy dashboard**.

Not affiliated with or endorsed by BKW.
## Features

- OAuth2 login (open BKW in the browser, paste the authorization code into Home Assistant)
- Automatic access-token refresh
- Configurable polling every **1–10** minutes (default **10**)
- Sensors:
  - **Consumption (latest day)** – kWh for the latest published portal day
  - **Consumption total** – cumulative kWh for the Energy dashboard

## Limitations

The myBKW portal API used here only provides **complete past calendar days**, not live “today so far” usage. During the day you typically see **yesterday’s** total (Swiss time, `Europe/Zurich`). After **midnight Swiss**, the next finished day appears once BKW publishes it.

There is no 15-minute or hourly data in the portal API today, so the integration is best for **daily history** and the **Energy dashboard**, not real-time load tracking.

## Requirements

- Home Assistant **2024.6.0** or newer
- BKW electricity customer with a **smart meter** and access to **[my.bkw.ch](https://my.bkw.ch/)** (energy charts visible after login)

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
2. Log in with your **myBKW** account.
3. After redirect to `https://my.bkw.ch/energy?code=...`, copy only the **`code`** value from the URL.
4. Paste the code into Home Assistant.

Codes expire quickly; if login fails, start the flow again.

### Metering point code (Messpunkt)

Enter your **metering point code** (*Messpunkt*), e.g. `CHXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX`.

**In the myBKW UI:** open **[Mein Energiemonitoring](https://my.bkw.ch/energy)** — the Messpunkt is shown there (same `CH…` number as in the portal).

**Alternatively (DevTools):** on the energy page, open **Strombezug**, then browser **DevTools → Network**, filter `metering-data`, and copy `meteringPointCode` from the request URL.

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
