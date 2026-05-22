# Google Calendar integration

Company calendar actions and planning tasks sync to a **dedicated Google Calendar** on each company owner's account (default name: **Idea Factory**, configurable via `GOOGLE_CALENDAR_PORTAL_NAME`). Events do not use the primary calendar unless you override the calendar ID.

## What syncs

- Actions scheduled from director discussions (`Schedule` / `Schedule selected`)
- Manual entries via **+ Add Action** on the company calendar
- Autonomous agent scheduling (when Self-Run mode schedules selected actions)

When an action is created or updated (date, title, description, status, completion notes), the linked Google event is created or updated. The event title is prefixed with the company name; completed actions show a ✓ prefix.

## User setup (company owner)

1. Sign in with the account that **owns** the company.
2. Click **Google Calendar** in the top navigation.
3. Click **Connect Google Calendar** and approve calendar access.
4. On connect (or when you turn **Enable sync** on), all existing **calendar actions** for your companies are pushed to Google in one batch. Use **Sync existing events** anytime to run that backfill again.
5. Enable **sync** and set **reminders** (minutes before the action date), e.g. `60,1440` for 1 hour and 1 day.
6. Schedule actions on any company calendar — they appear in Google Calendar.

**Note:** Violet **planning tasks** with a due date sync as separate Google events (prefixed with 📋). Tasks linked to a calendar action sync only via that action. **Analyze & optimize schedule** moves task due dates and updates Google Calendar for each moved task.

To pause sync without revoking Google access, uncheck **Enable sync** and save.

**Disconnect:** **Remove synced events on disconnect** is on by default. When checked, disconnect deletes Idea Factory events from Google and clears stored event IDs. Uncheck it before disconnecting if you want events to remain on Google.

## Administrator setup (one-time)

### 1. Google Cloud project

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a project.
3. **APIs & Services** → **Library** → enable **Google Calendar API**.

### 2. OAuth consent screen

1. **APIs & Services** → **OAuth consent screen**.
2. Choose **External** (or Internal for Workspace-only).
3. Add scope: `https://www.googleapis.com/auth/calendar` (full calendar access — needed to create the dedicated portal calendar and manage events).
4. Add test users if the app is in **Testing** mode (required until published).

### 3. OAuth client (Web application)

1. **Credentials** → **Create credentials** → **OAuth client ID** → **Web application**.
2. **Authorized redirect URIs** — add every URL users will use (exact match, trailing slash included):

   | Environment | Redirect URI |
   |-------------|----------------|
   | Production | `https://YOUR_HOST/settings/google-calendar/callback/` |
   | Local dev | `http://127.0.0.1:8000/settings/google-calendar/callback/` |

   Replace `YOUR_HOST` with `DJANGO_PUBLIC_HOST` (e.g. `manage.example.com`).

### 4. Server environment variables

Add to `idea_factory/.env`:

```env
GOOGLE_CALENDAR_CLIENT_ID=xxxx.apps.googleusercontent.com
GOOGLE_CALENDAR_CLIENT_SECRET=xxxx
# Optional: default reminders for new users (minutes before action date)
GOOGLE_CALENDAR_DEFAULT_REMINDERS=60,1440
# Optional: name of the dedicated Google Calendar (created on connect)
GOOGLE_CALENDAR_PORTAL_NAME=Idea Factory
```

Also ensure:

- `DJANGO_PUBLIC_HOST` matches your public hostname (used in event descriptions and OAuth redirect documentation).
- `CSRF_TRUSTED_ORIGINS` includes `https://YOUR_HOST`
- `ALLOWED_HOSTS` includes `YOUR_HOST`

Restart the application after changing `.env`.

### 5. Docker / production

Rebuild and redeploy the image after adding env vars and running migrations (`core.0005`, `ideas.0015`, and earlier Google Calendar migrations). Migrations run automatically via the container entrypoint.

After a scope change to full `calendar` access, owners should **disconnect and reconnect** Google Calendar once.

## Security notes

- OAuth tokens are stored encrypted (Django signing) on the user's `UserProfile`.
- Only the **company owner**'s connected calendar receives events for that company's actions.
- Use HTTPS in production; keep `GOOGLE_CALENDAR_CLIENT_SECRET` out of version control.

## Troubleshooting

| Issue | Check |
|-------|--------|
| "Server not configured" | `GOOGLE_CALENDAR_CLIENT_ID` and `GOOGLE_CALENDAR_CLIENT_SECRET` in `.env` |
| Redirect URI mismatch | Redirect URI in Google Console must match `https://HOST/settings/google-calendar/callback/` exactly |
| Access blocked (testing) | Add user's Google account under OAuth consent → Test users |
| Events not appearing | Owner must connect Google Calendar and enable sync; check application logs |
| Old actions missing in Google | Reconnect or toggle **Enable sync** off/on to run backfill; or edit/save the action |
| Optimize did not move Google events | Enable sync and connect Google; tasks need a **due date**; run **Sync existing events** once after deploy |
| Reminders wrong | User settings → reminder minutes (comma-separated) |

## Related code

- `apps/core/google_calendar.py` — OAuth and sync
- `apps/web/google_calendar_views.py` — settings UI
- `apps/core/signals.py` — sync on `CompanyCalendarAction` save
