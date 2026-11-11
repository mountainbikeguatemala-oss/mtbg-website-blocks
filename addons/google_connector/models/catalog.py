"""The Google apps the settings show as cards even before their module is installed (with Install): their module
declares the rest (scopes, settings) through google.connector._google_app_specs once installed."""
CATALOG = {
    # one card for every app reading a Gmail mailbox (Gmail's emails, Google Voice's texts): one switch, one access
    "gmail": {"label": "Gmail", "module": "cfd_channel_gmail", "sequence": 10,
              "description": "Gmail mailboxes read and answered: emails (Gmail channel), Google Voice texts "
                             "(Google Voice channel)."},
    "contacts": {"label": "Google Contacts", "module": "cfd_google_contacts", "sequence": 20,
                 "description": "Your contacts' Google photos (read only): Communication Flows' contacts without a "
                                "photo get theirs."},
    "calendar": {"label": "Google Calendar", "module": "mtbg_tours_google_calendar", "sequence": 30,
                 "description": "Shifts in each staff member's calendar, departures in a company calendar."},
    "maps": {"label": "Google Maps", "module": "mtbg_tours_google_maps", "sequence": 40, "needs_account": False,
             "uses_maps_key": True,
             "description": "Address search on forms, pickup points as map links and pictures."},
    "reviews": {"label": "Google Business Profile", "module": "mtbg_tours_reviews", "sequence": 50,
                "description": "Your Google Business Profile reviews, synced every day into Reviews (read only)."},
    "pagespeed": {"label": "PageSpeed Insights", "module": "mtbg_tours_page_speed", "sequence": 60,
                  "needs_account": False, "uses_server_key": True,
                  "description": "The website's speed, measured every night by Google (Lighthouse) for Page Speed's "
                                 "speed log."},
}

# the Google Cloud APIs each app needs switched on in the project (Set up Google › APIs: one link each)
APIS = {
    "gmail": [("gmail.googleapis.com", "Gmail API")],
    "contacts": [("people.googleapis.com", "People API")],
    "calendar": [("calendar-json.googleapis.com", "Google Calendar API")],
    "maps": [("places.googleapis.com", "Places API (New)"), ("geocoding-backend.googleapis.com", "Geocoding API"),
             ("static-maps-backend.googleapis.com", "Maps Static API"),
             ("maps-backend.googleapis.com", "Maps JavaScript API")],
    # Business Profile APIs are granted by Google on request (the project's access form) before they can be enabled
    "reviews": [("mybusinessaccountmanagement.googleapis.com", "My Business Account Management API"),
                ("mybusinessbusinessinformation.googleapis.com", "My Business Business Information API"),
                ("mybusiness.googleapis.com", "Google My Business API (reviews)")],
    "pagespeed": [("pagespeedonline.googleapis.com", "PageSpeed Insights API")],
}

# what an app shows only after its first read from Google (Set up Google's last step: say so, and open it there)
FIRST_SYNC = {
    "contacts": "The Google photo source stays empty until Google Contacts is read once: Open, Check (reads Google "
                "only, shows how many contacts it can fill), then Fill. After that it refreshes every night.",
    "calendar": "Nothing is in Google Calendar until its first sync: Open, choose the calendars, then Save and Sync "
                "now (this writes to Google Calendar and invites the staff to their shifts). After that it follows "
                "every change within the minute.",
    "reviews": "No review comes in until the review account finds its locations: Reviews › Accounts › the Google "
               "account › Find Locations, then Sync Now. After that the reviews sync every day.",
    "gmail": "New mail arrives within a few minutes of signing in. Older mail: Communication Flows › Channels › "
             "Gmail (or Google Voice) › history sync, for the period you choose.",
}
