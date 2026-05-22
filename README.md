# BKW Smart Meter – Home Assistant Integration

Unofficial Home Assistant custom integration that reads **grid consumption** from the [BKW customer portal](https://my.bkw.ch/) (daily totals), using the same APIs as the web app.

## Features

- OAuth2 login with PKCE (paste authorization code from browser redirect)
- Automatic access-token refresh
- Polls **P1D** metering data on a configurable interval (default **10** minutes, **1–10** allowed) for the **latest published portal day** (always a past date; BKW does not expose the current calendar day until it is complete)
- Sensors:
  - **Consumption (latest day)** (`sensor.*_latest_day`) – daily kWh for the latest published portal day (`data_date`, `period_start`, `period_end` attributes)
  - **Consumption total** – monotonic cumulative kWh for the Energy dashboard (adds each new published day once)

## Limitations

This integration only reflects what the BKW energy monitoring API provides today.

**No current-day consumption.** BKW publishes **complete past portal days** only. During the day, sensors show the **last finished Swiss calendar day** (typically “yesterday”), not how much you have used **so far today**. A new day appears after **midnight Europe/Zurich**, once that portal day is complete.

**Limited use for live optimisation.** Without same-day or short-interval data (e.g. last 15 minutes or last hour), it is hard to spot **large loads while they happen** and adjust behaviour in real time. The integration is strong for **daily totals**, **history**, and the **Energy dashboard** — not for “what am I using right now?”.

**Where the biggest gain would be.** The largest benefit for households would come from **BKW extending the API** so customers can access **current-day** values (ideally in 15-minute steps), even if marked **provisional** and corrected later. This project could then add sensors and automations for near-real-time use. Until BKW offers that officially, this integration stays within stable, documented P1D daily data.

## Requirements

- Home Assistant **2024.6.0** or newer (see `hacs.json`)
- BKW account with smart-meter data in [my.bkw.ch](https://my.bkw.ch/)
- HTTPS is **not** required for this integration (auth uses a manual code paste, not HA’s OAuth callback)

## Installation

### Option A: Copy to `custom_components`

1. Copy the folder `custom_components/bkw_smartmeter` into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and search for **BKW Smart Meter**.

### Option B: HACS (custom repository)

1. In HACS → **Integrations** → **Custom repositories**, add  
   `https://github.com/pavax/home-assistant-bkw-smartmeter`  
   and category **Integration**.
2. Install **BKW Smart Meter** from HACS.
3. Restart Home Assistant and add the integration as above.

**Stay on latest `master`:** HACS uses this repo’s GitHub default branch (`master`). There is no `default_branch` key in `hacs.json`; do not set `hide_default_branch` in `hacs.json` (that would hide branch installs).

- **First install (HACS 2.x):** If the download dialog offers a version, choose **master** / default branch. If only a commit hash appears, use **Developer tools → Actions → `update.install`** on the BKW Smart Meter update entity with `version: master` instead (commit-only installs can 404).
- **Updates:** Open the **BKW Smart Meter** update entity → **Install**, set version to **`master`** to pull the current tip of `master`.

**Optional — pinned releases:** [Create a GitHub release](https://github.com/pavax/home-assistant-bkw-smartmeter/releases/new) (e.g. `v0.4.1` matching `manifest.json`) if you prefer version tags over tracking `master`.

## Configuration

### 1. Log in (PKCE)

1. Start the config flow; Home Assistant shows an **authorize URL**.
2. Open that URL in a browser and log in to BKW.
3. After redirect to `https://my.bkw.ch/energy?code=...`, copy the **`code`** query parameter (not the full URL).
4. Paste the code into Home Assistant.

Codes are short-lived; if exchange fails, restart the flow to get a new link.

### 2. Metering point code

Enter your **metering point code** (`meteringPointCode`), e.g. `CH1022201234500000000000000196130`.

**How to find it**

1. Open [my.bkw.ch/energy](https://my.bkw.ch/energy) and open the **Strombezug** (or relevant) chart.
2. Open browser DevTools → **Network**, filter for `metering-data`.
3. Copy the value of `meteringPointCode` from the request URL.

### 3. Data type (advanced)

BKW’s `dataType` names do **not** match plain English. For many meters (verified on my.bkw.ch):

| Portal chart | `dataType` |
|--------------|------------|
| **Strombezug** (grid import) | `PRODUCTION_BKW` |
| Other channel (e.g. solar feed-in) | `CONSUMPTION_BKW` (check your portal) |

Default: **`PRODUCTION_BKW`** (= Strombezug). If setup fails with a 400 error:

1. Open the chart you want on [my.bkw.ch/energy](https://my.bkw.ch/energy).
2. In DevTools → Network, find a successful `metering-data` request.
3. Copy the exact `dataType` from that request.
4. Enter it in the config flow or under **Configure → Options**.

### 4. Update interval

Under **Configure → Options**, set **Update interval (minutes)** (**1–10**) and/or **Data type**. The maximum is capped at 10 minutes because BKW refresh tokens expire after 15 minutes (`refresh_expires_in`); polling must run more often than that to keep the session alive. Saving triggers an **immediate** data fetch and applies the new interval without a full restart.

See **Limitations** above for why the latest day is not “today” during the day.

### Time zone

Days follow the **Swiss calendar** (`Europe/Zurich`). Sensor dates and `period_start` / `period_end` are local; the BKW API is called with the equivalent UTC range. A new portal day is fetched after **midnight Swiss**, once that day is complete (see **Limitations**).

## Energy dashboard

1. **Settings → Dashboards → Energy**
2. Add **Grid consumption** and select **Consumption total** (or configure grid consumption to use the total_increasing sensor).

## Re-authentication

BKW refresh tokens expire relatively quickly. If sensors stop updating or you see a reauth notification:

1. Open the integration → **Reconfigure** (or remove and add again).
2. Complete the PKCE login steps again.

## Security and disclaimer

- This is an **unofficial**, reverse-engineered integration. BKW may change APIs without notice.
- Tokens are stored in your Home Assistant config entry only.
- Do not share network captures or logs containing tokens.
- Use at your own risk; comply with [BKW terms of use](https://www.bkw.ch/).

## Development

```bash
python -m compileall custom_components/bkw_smartmeter
```

### Docker verification

Smoke-test the integration in Home Assistant. Config and `custom_components/bkw_smartmeter` are bind-mounted in `scripts/bkw-smartmeter-ha-verify/docker-compose.yml` (live edits apply after container restart).

From the **repository root**:

```bash
./scripts/verify-docker.sh
```

Manual start/stop:

```bash
docker compose -f scripts/bkw-smartmeter-ha-verify/docker-compose.yml \
  --project-directory scripts/bkw-smartmeter-ha-verify up -d

docker compose -f scripts/bkw-smartmeter-ha-verify/docker-compose.yml \
  --project-directory scripts/bkw-smartmeter-ha-verify down
```

Then open **http://127.0.0.1:8123** → **Settings → Devices & services → Add integration** → **BKW Smart Meter**.

## License

MIT (see repository license file if present).
