# Google OAuth Scope Justification

**Application:** До встречи (Do Vstrechi)  
**Homepage:** https://dovstrechiapp.ru  
**Privacy Policy:** https://dovstrechiapp.ru/privacy  
**Description:** Meeting scheduling Telegram Mini App (Calendly alternative)

---

## Scope: `https://www.googleapis.com/auth/calendar.events`

**Why this scope is necessary:**

До встречи (Do Vstrechi) is a meeting scheduling application built as a Telegram Mini App, similar to Calendly. Users (organizers) create time-slot schedules and share a booking link. Guests open the link and choose an available slot to book a meeting.

We need `calendar.events` for three specific operations:

### 1. Read events — availability checking
When a guest views the organizer's available slots, our app reads the organizer's Google Calendar events to identify busy periods. Any time slot that overlaps with an existing calendar event is hidden from the guest, preventing double-booking.

**User experience:** The organizer connects their Google Calendar once. From that point on, their booking page automatically reflects real availability — no manual blocking of slots needed.

### 2. Create events — booking confirmation
When a guest successfully books a meeting, we automatically create a Google Calendar event in the organizer's calendar containing: meeting title, start/end time, guest name, guest contact, and a Jitsi video call link. This ensures the meeting appears in the organizer's calendar with all relevant information.

### 3. Delete events — cancellation sync
When a booking is cancelled (by either organizer or guest), we delete the corresponding Google Calendar event to keep the organizer's calendar in sync with the app state.

**Why `calendar.readonly` is not sufficient:**  
The `calendar.readonly` scope only allows reading. We need to create and delete events (operations 2 and 3 above), which requires the broader `calendar.events` scope. However, `calendar.events` is still a **sensitive** scope, not a restricted one — we do not access calendar metadata, share data with third parties, or use data for advertising.

---

## Scope: `https://www.googleapis.com/auth/userinfo.email`

**Why this scope is necessary:**

After a user connects their Google Calendar, we display the connected account's email address in the app's calendar settings screen (e.g., "Connected: user@gmail.com"). This helps users identify which Google account is linked and confirm the connection was successful.

We use **only the email address** from this scope — no other profile data (name, photo, etc.) is accessed or stored.

---

## Limited Use Compliance

Our use of Google Calendar data strictly adheres to the [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy) Limited Use requirements:

- Data is used **only** to provide the scheduling/booking functionality described above.
- We do **not** share calendar data with third parties.
- We do **not** use calendar data for advertising or user profiling.
- We do **not** sell calendar data.
- Access tokens are stored encrypted on our server (Fernet/AES encryption).
- Users can revoke access and delete all stored data at any time via the app settings.
