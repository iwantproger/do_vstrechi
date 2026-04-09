# Google OAuth Verification — Demo Video Script

**Video requirements:** Unlisted YouTube, 2–5 minutes, English audio or subtitles.

---

## Scene 1: Introduction (0:00 – 0:20)

**On screen:** Browser open to https://dovstrechiapp.ru

> "This is Do Vstrechi — a meeting scheduling app built as a Telegram Mini App, similar to Calendly. I'll demonstrate how the Google Calendar integration works and why we need the requested OAuth scopes."

---

## Scene 2: App Overview (0:20 – 0:40)

**On screen:** Open Telegram, launch @do_vstrechi_bot

> "The app runs inside Telegram. An organizer creates a scheduling page with available time slots, then shares a link. Guests open the link and pick a time to book a meeting."

Show: Main screen of the Mini App with schedules list.

---

## Scene 3: Connecting Google Calendar (0:40 – 1:30)

**On screen:** Navigate to Profile → External Calendars in the Mini App

> "To connect Google Calendar, the user goes to External Calendars and taps 'Connect' next to Google Calendar."

Show: The calendar settings screen with provider list.

> "Tapping 'Connect' opens Google's authorization screen in the browser."

**On screen:** Google OAuth consent screen showing:
- App name: **До встречи (Do Vstrechi)**
- Requested scope: **See, edit, share, and permanently delete all the calendars you can access using Google Calendar** (calendar.events)
- App logo and verified domain

> "The user sees exactly what access is being requested and chooses their Google account."

Show: User clicks "Allow". Google redirects back.

> "After authorization, the app confirms the calendar is connected and displays the linked email address."

**On screen:** Calendar settings showing connected Google account with email.

---

## Scene 4: Scope Usage — Reading (Availability Check) (1:30 – 2:15)

**On screen:** Organizer's booking page (open in browser, no Telegram needed)

> "This is the organizer's public booking page. When a guest selects a date..."

Show: Guest tapping a date on the calendar widget.

> "...the app checks the organizer's Google Calendar for that day. Time slots that overlap with existing Google Calendar events are automatically hidden."

Show: Some time slots greyed out (blocked by existing calendar events).

> "This prevents double-booking without any manual work from the organizer. This is why we need read access to calendar events."

---

## Scene 5: Scope Usage — Creating Events (2:15 – 3:00)

**On screen:** Guest completing a booking

> "When a guest books a meeting, they enter their name and confirm."

Show: Guest fills in name, taps "Book".

> "The booking is confirmed. Simultaneously, the app creates a Google Calendar event in the organizer's calendar."

**On screen:** Google Calendar (organizer's view) — new event appears with:
- Meeting title
- Correct time
- Guest name in description
- Video call link (Jitsi)

> "The organizer sees the meeting directly in Google Calendar with all relevant details. This is why we need write access — `calendar.events` scope."

---

## Scene 6: Scope Usage — Deleting Events (3:00 – 3:30)

**On screen:** Organizer cancels the meeting in the app

> "If the organizer cancels the meeting..."

Show: Organizer taps "Cancel" on the booking.

> "...the app immediately deletes the corresponding Google Calendar event."

**On screen:** Google Calendar — the event is gone.

> "This keeps Google Calendar in sync with the app state."

---

## Scene 7: Disconnecting (3:30 – 3:50)

**On screen:** Profile → External Calendars → Disconnect

> "Users can disconnect Google Calendar at any time. Upon disconnection, all stored tokens and cached event data are permanently deleted from our servers."

Show: Tap "Disconnect" → confirmation → Google account removed from list.

---

## Scene 8: Closing (3:50 – 4:00)

> "That's the complete Google Calendar integration in Do Vstrechi. We use `calendar.events` to read availability, create bookings, and delete cancelled meetings. We use `userinfo.email` to display the connected account email. No data is shared with third parties or used for advertising."

**On screen:** https://dovstrechiapp.ru/privacy

---

## Recording Tips

- Use a screen recorder with audio (OBS, Loom, QuickTime)
- Record at 1080p
- Speak clearly in English (or add English subtitles)
- Show the Google consent screen clearly — make sure app name is visible
- Upload to YouTube as **Unlisted** (not Private — reviewers need to access it)
- Disable comments on the video
