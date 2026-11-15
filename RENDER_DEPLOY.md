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
- `KOTAK_TOTP_SECRET`
- `KOTAK_ENVIRONMENT`
- `REACTION_ALPHA_WEBHOOK_SECRET`

Then change:

- `REACTION_ALPHA_SIMULATED=false`
- `REACTION_ALPHA_SIM_ALWAYS_OPEN=false`

After Render redeploys, the app can automatically generate fresh TOTP codes if `KOTAK_TOTP_SECRET` contains the permanent authenticator setup key. Keep this key in Render secrets, never in Git. For manual login, leave it unset. Open any live page: if Kotak needs a code, the page shows the login form first and resumes at the same URL after login. A restored session or simulated page does not need a code. Set `REACTION_ALPHA_WEBHOOK_SECRET` on a public deployment and enter that value in the admin secret field for manual login.

`KOTAK_TOTP_SECRET` must be the permanent authenticator setup key, not the current 6-digit code shown in the authenticator app. A 6-digit code expires quickly and cannot keep Kotak always available after a redeploy, restart, or screen lock.

Optional Telegram alerts:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Notes

- Render provides the public app URL after the first successful deploy.
- The free web-service plan can sleep when idle, so use a paid instance for serious live-market use.
- Paper-trade data uses `/tmp` on Render in this config, so it is not persistent across restarts.
- Kotak live mode uses the official `kotakneoapi` PyPI package pinned in `requirements.txt`. When migrating from the legacy Git-installed SDK, clear the Render build cache and deploy once so the two packages do not share an import directory.
