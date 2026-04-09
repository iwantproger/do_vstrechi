# Google OAuth Verification Checklist

## Pre-submission Requirements

### ✅ Pages live on prod domain
- [ ] https://dovstrechiapp.ru/privacy — Privacy Policy (RU + EN)
- [ ] https://dovstrechiapp.ru/terms — Terms of Service (RU + EN)
- [ ] Both pages accessible without Telegram, without login

### ✅ Google Cloud Console — OAuth Consent Screen

| Field | Value | Status |
|-------|-------|--------|
| App name | До встречи (Do Vstrechi) | Fill in |
| User support email | support@dovstrechiapp.ru | Fill in |
| App logo | 120×120px PNG (see design/app_icon_512.png, resize) | Upload |
| Application home page | https://dovstrechiapp.ru | Fill in |
| Privacy Policy URL | https://dovstrechiapp.ru/privacy | Fill in |
| Terms of Service URL | https://dovstrechiapp.ru/terms | Fill in |
| Authorized domains | dovstrechiapp.ru | Fill in |
| Developer contact email | support@dovstrechiapp.ru | Fill in |

### ✅ Scopes
Current scopes after optimization:
- `https://www.googleapis.com/auth/calendar.events` — sensitive
- `https://www.googleapis.com/auth/userinfo.email` — non-sensitive

**Removed:** `calendar.readonly` (redundant — `calendar.events` covers reading)

### ✅ Domain Verification
- [ ] Verify `dovstrechiapp.ru` in [Google Search Console](https://search.google.com/search-console)
- [ ] Method: HTML file upload OR DNS TXT record
- [ ] Add verified domain to Authorized Domains in OAuth Consent Screen

### ✅ Demo Video
- [ ] Record unlisted YouTube video (2–5 min, English)
- [ ] Script: see `docs/google-verification-video-script.md`
- [ ] Upload to YouTube as **Unlisted**
- [ ] Copy video URL for submission form

---

## Submission Steps

1. Go to [Google Cloud Console](https://console.cloud.google.com) → APIs & Services → OAuth Consent Screen
2. Click **"Prepare for Verification"** (or Edit App)
3. Fill in all fields from the table above
4. Under **Scopes** → click "Add or Remove Scopes" → verify only `calendar.events` + `userinfo.email`
5. Under **Test users** → remove all test users (or keep for fallback)
6. Click **"Submit for Verification"**
7. In the verification form:
   - Paste Privacy Policy URL
   - Paste Terms of Service URL
   - Paste YouTube demo video URL
   - For `calendar.events`: paste justification from `docs/google-verification-justification.md`
   - For `userinfo.email`: "We display the connected Google account email in the app settings."

---

## Timeline

- Google typically responds within **4–6 weeks** for sensitive scopes
- During review: app works for up to 100 test users without the warning screen
- After approval: "This app is unsafe" warning disappears for all users

---

## Notes

- **Security Assessment (CASA) is NOT required** — only for restricted scopes. Our scopes are sensitive, not restricted.
- If rejected, Google sends an email with specific reasons — address them and resubmit.
- Keep the demo video unlisted (not private) so Google reviewers can access it.
