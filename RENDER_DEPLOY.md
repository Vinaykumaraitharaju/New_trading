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

### Keep the learner on free hosting

1. Keep the Render web service on Free. Create a dedicated database in [Turso Free](https://turso.tech/pricing). Use a hosted **libSQL database** compatible with [SQL over HTTP](https://docs.turso.tech/sdk/http/reference).
2. In the existing Render service's Environment settings, set `TURSO_DATABASE_URL` to the database URL (libsql:// or https://) and `TURSO_AUTH_TOKEN` to a database-scoped read/write token. Never put the token in Git or chat. Use the **same database** across commits. No pip package, disk, paid model, or extra worker service is needed.
3. Open **the primary workspace** at /history?tab=performance. Experience memory should show **Cloud connected**. The separate /demo workspace deliberately stays local. A simulated primary workspace uploads simulated examples only; live mode never learns from those examples.
4. Wait for a verified 30-minute label and for **Pending uploads: 0**. Compare the previous-session sample counts before and after a redeploy. Same-day outcomes become eligible next session. Empty counts initially are normal. A status of **Local only** or **Sync failed** is not proof of durability.

The replicated data is a private, append-only learning set: source, symbol, setup, original direction, publication time, completion day, measured direction and any frozen shadow prediction. It is **not a backup of the SQLite paper journal**, open positions, incomplete trials, broker session, or all archive rows. Up to 100 examples are sent per batch; uploads are retried idempotently. Only acknowledged rows are durable. A process killed before acknowledgment can lose unsynced local rows. Render sleep means there are no new observations while asleep. If the existing instance has valuable local data, export it before changing its environment or triggering deployment; a new release cannot rescue a deleted /tmp database.

The learner counts actual UP/DOWN/NEUTRAL labels from earlier IST sessions for the same source, setup and original direction. With fewer than 30 measured outcomes, fewer than five distinct completion dates, or a tied leading label, it abstains. Otherwise it freezes the most frequent direction as a **shadow forecast**. These are provisional evidence thresholds, not demonstrated profitability. Paired results compare the original and shadow calls on the same measured observations. Resetting the paper journal does not erase the independent learning set. Stay within the provider's free quotas; do not enable paid overages.

- Render provides the public app URL after the first successful deploy.
- The free web-service plan can sleep when idle, so use a paid instance for serious live-market use.
- Paper-trade data uses `/tmp` on Render in this config, so it is not persistent across restarts.
- Kotak live mode uses the official `kotakneoapi` PyPI package pinned in `requirements.txt`. When migrating from the legacy Git-installed SDK, clear the Render build cache and deploy once so the two packages do not share an import directory.
