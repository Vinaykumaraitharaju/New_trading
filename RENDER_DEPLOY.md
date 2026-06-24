# Render Deployment

This project is configured for Render with `render.yaml`.

## First deploy

1. Open Render and create a new Blueprint from the GitHub repository:
   `Vinaykumaraitharaju/New_trading`
2. Render will read `render.yaml` from the repository root.
3. The first deployment starts in simulated mode so the site can boot without broker secrets.

## Live Kotak mode

In the Render service settings, add these environment variables as secrets:

- `KOTAK_CONSUMER_KEY`
- `KOTAK_MOBILE_NUMBER`
- `KOTAK_UCC`
- `KOTAK_MPIN`
- `KOTAK_ENVIRONMENT`
- `REACTION_ALPHA_WEBHOOK_SECRET`

Then change:

- `REACTION_ALPHA_SIMULATED=false`
- `REACTION_ALPHA_SIM_ALWAYS_OPEN=false`

After Render redeploys, open `/kotak-login` on your Render app URL and enter the current 6-digit authenticator code. If `REACTION_ALPHA_WEBHOOK_SECRET` is set, enter that same value in the admin secret field.

`KOTAK_TOTP_SECRET` is optional. Use it only if you have the permanent authenticator setup key and want fully automatic re-login.

Optional Telegram alerts:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Notes

- Render provides the public app URL after the first successful deploy.
- The free web-service plan can sleep when idle, so use a paid instance for serious live-market use.
- Paper-trade data uses `/tmp` on Render in this config, so it is not persistent across restarts.
- Kotak live mode requires the Kotak Neo SDK, which is installed from GitHub through `requirements.txt`.
