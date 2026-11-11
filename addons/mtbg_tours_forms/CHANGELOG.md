# Changelog

Every version of this extension, newest first. Tags: `git tag -l 'mtbg_tours_forms-*'`.

## 19.0.0.6.0 (2026-11-11)

- **Joins the universal repository** (owner, 2026-11-11, the split, step 3): its folder moves from the Tours repository
  to the website blocks' (technical name kept; ``mtbg_github_source`` names it), so a plain Odoo website gets it
  without Tours. Nothing changes on a page or in a form.
- The messaging terms and the Form Designer's languages are read with the admin look's translated text settings
  (mtbg_backend_ui 0.1.0: ``ir.config_parameter.mtbg_get_text`` / ``mtbg_text_langs``, the same system parameters
  and fallbacks); Forms' own read-only copy (models/texts.py) goes. Depends on mtbg_backend_ui.

## 19.0.0.5.0 (2026-11-11)

- **Forms needs no Tours Core** (owner, 2026-11-11: universal modules out of Tours; next, it moves to the Website
  Blocks repository): it depends on Odoo's website (and the website blocks' base for the shared chat helper).
  - Who may change the forms: website designers, plus Tours managers where Tours is installed (Booking Form's access
    rules); reading them: every internal user. The Form Designer asks "can write forms" instead of a Tours group.
  - Tours Core's contact rule, one open lead per person, first-touch lead sources and WhatsApp opt-in field are used
    where installed; on a plain website a form's contact is found by email or mobile (else made), a new lead takes
    the form's source.
  - The messaging terms are read by Forms itself (models/texts.py: the same `key` / `key@lang` settings as Tours
    Core's translated texts, so a site's saved wording reads the same); their editor and built-in texts' copy are
    Booking Form's, on Tours Core's settings page as before. Text settings join the universal admin home later.
  - Tour pages are Booking Form's: what a sidebar form is about, the popups' tour / rental page rules, the
    designer's tour previews, the contact popup's tour covers.
  - Removed: the unused trip dates and riders checks and components (no form or module used them).
  - The chat helper is the website blocks' (`@mtbg_tours_content_blocks/shared/chat`, Reusable Blocks 0.11.2).

## 19.0.0.4.18 (2026-11-10)

- The default messaging terms (until the owner's wording is saved) fill in the company's name and email (`%(company)s`, `%(email)s`); the saved wording is kept. Brand-free release (owner, 2026-11-10): no business names in code, data, samples, comments or tests.

## 19.0.0.4.17 (2026-11-10)

- Click tracking for Communication Flows' Website Visitors 1.4.0: the newsletter form's send button carries
  `data-cfd-track="newsletter"` (no ref). Other forms' sends unchanged.

## 19.0.0.4.15 (2026-11-08)

- Source Channel history: form leads without a source map to their form by where they came from (newsletter, phone menu, contact page/popup, tour page). Needs Core 0.5.56.

## 19.0.0.4.12 · 2026-11-04

- **The popups hide the website chat with Core's shared helper** (`@mtbg_tours_core/shared/chat`; owner, 2026-11-04, JS consolidation part C): the copy in `contact_form.js` is gone.

## 19.0.0.4.11 · 2026-11-03

- Spanish (bulk translation pass): the .pot regenerated from Odoo's export and es.po rebuilt from it; 196 new Spanish translations. No English text changed.

## 19.0.0.4.10 · 2026-11-03

- **Alt text on the mobile field's flag** (owner, 2026-11-03: "Alt text for every image on the page"): the flag by
  the dial code is named after its country ("Guatemala"), in the page's language, and follows the country picked
  (`showPhoneCountry` in `fields.js`, shared by the booking, contact, chat and pre-tour forms). It was alt="" on every
  page of the site (626 flags on www).

## 19.0.0.4.9 · 2026-10-30

- **Lighter pages** (owner, 2026-10-30: page speed round 2): every phone field sent its whole country list (about
  240 countries with their dial codes, lengths and flags) with the page: 801 options and a third of a tour page's
  HTML (317 → 214 KB on webspeed), and the server built each one (tour page 0.17 → 0.12 s). A phone field now
  comes with the country it opens on only; the page carries the list once (compact, about 4 KB compressed), and
  each field's picker is filled from it the moment it is touched (pointer, focus or key), when its number already
  has a dial code, or once the page is idle. `window.mtbgPhoneFill(root)` fills them at once for a script that
  reads the options. What the visitor sees and picks is unchanged.

## 19.0.0.4.8 · 2026-10-30

- The contact and newsletter popups are dialogs for screen readers (`role="dialog"` with their label; accessibility,
  page speed phase 4).

## 19.0.0.4.7 · 2026-10-30

- **No Google font on every page** (owner, 2026-10-30: page speed): the newsletter popup no longer links Alfa Slab
  One; its heading already uses the site's own heading font (Website › Theme), so nothing changes on screen and
  every page loads one render-blocking stylesheet less.

## 19.0.0.4.6 · 2026-10-30

- **The phone field on a cached page opens on the visitor's own country** (page speed, phase 3): the field opened on
  the country chosen while the page was built; on a page from Cloudflare's cache (Cloudflare Page Cache extension)
  that is the first visitor's. A field with no number yet is marked (`data-mtbg-open="visitor"`) and, once the
  visitor starts filling the form, opens on their country from their own session (`window.mtbgSession`), unless they
  picked one or typed a number. Without the page cache nothing changes.

## 19.0.0.4.5 · 2026-10-29

- Contact, question and newsletter forms find and update the contact by Core's contact rule (the most complete
  wins, each change in the chatter) and add to the person's one open lead. The browser's website visitor is linked
  to the contact (CFD website visitors 1.1.0's `_cfd_link_request`; nothing without it, never failing the submit).

## 19.0.0.4.4 · 2026-10-28

- **Phone pickers on shared dial codes** (owner, 2026-10-28: a US contact's +1 number opened on a Caribbean flag): a
  number on file opens on the contact's own country when it shares that dial code (+1, +7, +44, +61, +47, +262, +590,
  +599…), else the area code's country (443: the US, 416: Canada, 268: Antigua), else the code's main one (US for +1).
- A dial code several countries share never replaces a country the contact has (`_mtbg_fill_country`); an empty
  country is still filled, and a code of one country still keeps the latest the person chose.

## 19.0.0.4.3 · 2026-10-28

- SMS terms placement (owner, PHASE-5): the contact forms (contact page, tour sidebar, contact popups, phone menu) ask
  for no texting consent any more: their SMS / WhatsApp boxes and fine print are gone (booking texts are consented to
  on the booking form, which shows the **Booking texts** terms once a phone number is typed). Only the newsletter
  popup asks, for promotional texts, with the **Promotional texts** terms. Consents already stored stay as they are.

## 19.0.0.4.2 · 2026-10-28

- **Texting consent, two kinds** (owner, for the Twilio toll-free verification; carriers need them apart): the
  contact forms ask for texts in reply to the enquiry and about the booking (SMS and WhatsApp boxes, no marketing);
  the marketing popup (a form that signs up for the newsletter) has one box for promotional texts (up to 4 a month).
  EN + ES, the Privacy Policy and Terms of Service links with both.
- **Messaging terms** (owner: "two editable global fields"): the two texts are settings in every language of the site,
  edited in one place, Core's settings page › **Messaging terms**: **Booking texts** (`mtbg_tours.messaging_terms_booking`:
  the contact forms' SMS / WhatsApp boxes, and the booking form's line) and **Promotional texts**
  (`mtbg_tours.messaging_terms_promotions`: the marketing popup's box). Every form reads them; the owner's Twilio
  wording is copied in on install / update.
- What is stored on the contact with each box is the wording shown, in the visitor's language: the booking texts in
  "Consent Wording" (as before), the promotions in their own flag, date and wording: new contact fields
  `mtbg_sms_marketing_opt_in` / `_date` / `_text`, defined here so the booking form (which depends on Forms) writes
  the same ones. The server takes only the boxes the form shows. Every box stays optional and unticked.
- Fix: the contact page's, tour sidebar's and popups' SMS / WhatsApp ticks were never sent (only the old newsletter
  form sent them), so those opt-ins were lost. They are sent now, and a ticked box asks for the mobile number.

## 19.0.0.4.1 · 2026-10-27

- Fix: the Form Designer's form list waits while a save is running. Switching forms then was undone when the save
  finished (it reloads the saved form).

## 19.0.0.4.0 · 2026-10-26

- **Popup forms** (the owner, 2026-10-26): any website form can be a popup (Form Designer > **Popup**: "Show as a
  popup"). It opens by itself after 3 minutes or when the visitor leaves the page (computers), once a visit, on the
  pages its rule takes: **All pages** or **Only these pages** (homepage, tour pages, rental pages, blog, contact page,
  and pages whose address contains given words) and **Never on** (the same choices). On a page only the first popup
  in their order opens (the Popup tab's list, its arrows).
- A popup's **look**: **Full photo** (the form over the picture, as the newsletter popup) or **Photo beside** (as the
  contact popup); its **background pictures** (uploaded, in order), **rotate** (a different picture each opening, or
  always the first), the **photo overlay** (how dark), a **logo**, and the **dark bar at the bottom** (its words,
  translatable, its colour and its text colour; with the Privacy Policy link on the full look).
- **Sending it signs up for the newsletter**: a form switch (subscribed, tagged Newsletter, their language and
  opt-ins, as the newsletter popup always did; its lead "Newsletter signup").
- The hand-made **newsletter popup** of 2025 becomes such a form, "Newsletter popup" (the update makes it): its
  heading, Name, Email, Mobile, texting opt-ins and Subscribe button, its pictures, logo, overlay, yellow button and
  offer bar, on every page but the tour and rental pages, as before; it still opens from "Subscribe to our
  Newsletter".
- **Pre-tour header and step titles** (with Pre-tour 19.0.0.2.12): the header's title has a level (H1 as before, or
  H2-H5), a colour (light and dark pages), bold, uppercase and alignment, its subtitle bold, uppercase and alignment
  (Messages tab); each step's title has a colour, bold, uppercase and alignment (its block's settings). The fonts and
  sizes stay the theme's. Nothing set: as before.
- **No more text size sliders** (the owner, 2026-10-27: "they are not working"): a block's text size is gone from
  the designer and no longer applied (the theme's size).
- The designer's **preview of a popup form** shows it in its popup (its unsaved pictures, overlay, logo and dark
  bar); **Preview the popup** on the Popup tab.

## 19.0.0.3.13 · 2026-10-26

- **Text size** (Style tab) now works: the form's texts, fields and button are sized in em, so the slider scales them
  (the headings keep the theme's sizes).
- **Each block's text** (its settings in the designer): a **Text size** (70-150 % of the form's) and a **Colour**, one
  for light pages and one for dark pages (the preview's light / dark switch says which you set; empty: the form's).
- **Heading level** for a Heading block: **H3 / H4 / H5**, real headings, their font and size the website theme's.
- A heading follows the Style tab's **Labels and titles** colour when it is set (light and dark looks); before, it
  kept the theme's heading colour (white on the dark sidebar).

## 19.0.0.3.12 · 2026-10-26

- **Light and Dark looks**: the Form Designer stores the Style tab's values per mode: set them with the preview's
  light / dark switch on dark (moon) and they are the variant's look on dark pages (a tour's Page Theme: Dark, which
  puts `.mtbg-theme-dark` on the page), token by token over the light look (a value left empty stays the light
  one's). Stored as `<variant>:dark` in the form's style.

## 19.0.0.3.11 · 2026-10-26

- Under the booking form (the tour page's sidebar), **Send message is an outline** in normal weight (thin light border,
  grey text, filling in softly on hover), so Book Now above it stands out. A button colour set on the Style tab
  (Tour sidebar) still paints it.

## 19.0.0.3.10 · 2026-10-26

- **Menu Contact Form**: a form of its own for the phone menu (Forms › Menu Contact Form), so it can change without
  touching the contact form. The menu's Contact us opens it (the contact form if it's deleted). Name, mobile, email,
  message; dark mode on the menu's navy: transparent background and fields, light text, a soft border. EN + ES.
- **One Name field** everywhere (the owner: never first and last name apart): the contact form's First / Last name
  become one Name field (the update merges them in every website form, rules included), and the newsletter popup
  asks for one name. Forms still accept first + last name from older blocks. A lead from the phone menu says so.

## 19.0.0.3.8 · 2026-10-26

- The contact form has a **Phone menu** look of its own (Form Designer › Style › Phone menu; the update adds the
  variant to the contact form): the phone menu's Contact us shows it, so it can sit dark on the menu's navy.
  Backgrounds may be **transparent**; the placeholders and the consent link follow the look's colours; 16px inputs
  (no zoom on iPhones).
- The newsletter and contact popups hide the website chat while open (shared html.cfd-chat-hidden).

## 19.0.0.3.7 · 2026-10-25

- Newsletter popup: the close X is transparent (white strokes with a shadow, still a 40px tap target); on phones the
  form is centred on the screen (taller than the screen: it scrolls from the top, nothing cut off) and the X stays
  clear of the notch.
- **Contact form in the phone menu**: the menu's Contact us button (mtbg_tours_website) opens the Form Designer's
  contact form over the menu, drawn on the first tap (the Form block); without this extension it links to the page.
- Contact form in the sidebar: the consent link follows the Style tab (the accent mixed with the text colour), no
  more fixed pale blue.

## 19.0.0.3.6 · 2026-10-25

- Headings take their font, size and weight from the website's theme options only (the owner: "set directly in
  Odoo"): no font-family, font-size or font-weight of our own on the contact page and form titles, the newsletter popup's title, the form steps' titles. Colours and spacing stay.

## 19.0.0.3.5 · 2026-10-25

- "Chat with us" links (#livechat) open the website chat whatever its state: a chat window already open gets the
  focus, a folded chat (its bubble) opens, else a new chat starts; a page without a chat (switched off, no operator)
  opens the contact popup instead. Before, they did nothing once the visitor had a chat.
- A chat-only page, **/chat**, for links in emails (the owner): no menu or footer, the logo, and the website chat opens
  by itself (the contact popup when no chat is available within a few seconds).

## 19.0.0.3.4 · 2026-10-25

- No newsletter popup on tour and rental pages (the owner): nothing interrupts a booking (it still opens elsewhere).
- The website chat (bubble and window) hides while the contact or newsletter popup is open (with Website Chat 2.1.0).

## 19.0.0.3.3 · 2026-10-25

- The newsletter popup is full screen on phones (the owner), like the booking popups.

## 19.0.0.3.2 · 2026-10-23

- A form sets the contact's **country** from the mobile they type: the country picked in the phone field's country picker is kept, even over another one (the latest they chose; +1 told apart as US or Canada); without a pick, the number's own region fills an empty country only. On every website form and the newsletter popup; shared with the other extensions (`res.partner._mtbg_fill_country`).

## 19.0.0.3.1 · 2026-10-22

- One editor: the Forms page has no sections any more. An extension that adds a type of form adds **tabs to the Form Designer**, shown when one of its forms is open (registry `mtbg_form_designer_extensions`), saved and discarded with the designer's Save / Discard.

## 19.0.0.3.0 · 2026-10-22

- Renamed **Forms** (it was Form Fields; the technical name stays `mtbg_tours_forms`).
- Its page is the **Forms** page: every form of the site in one place. The Form Designer's form list shows them all, grouped (the website's forms, then each extension's, e.g. Pre-tour forms). Extensions add sections of their own beside the designer (registry `mtbg_forms_sections`): with Pre-tour Forms & Waivers installed, its forms, waivers and riders' forms are a section here, and Edit opens a form in the designer. A section keeps its unsaved changes while another is shown.
- The form list ends each type with its own **+ New**: "+ New website form" (a copy of the website form open, else the contact form, named "New form N"; sent, it makes a contact and a CRM lead like the contact form) and, with Pre-tour Forms & Waivers, "+ New pre-tour form". The open form's **name** is edited right next to the list (it was in Messages).
- **Form block** (website editor > Contact & Forms > Form): any website form on any page, chosen in the block's options. The page keeps only the form's key; the form is drawn on each visit, so the designer's changes show everywhere at once.

## 19.0.0.2.1 · 2026-10-22

- The preview shows only its content: no website header. Its bar has the language (also of the texts edited; it moved there from the top of the page), the currency (the site's base and second currency, when one is set), a light / dark page (the site's dark page look) next to desktop / phone. The form switches (variant, known visitor, preview as, show every block) move to a second row of the bar.

## 19.0.0.2.0 · 2026-10-22

- **Form Designer** (this extension's tile): a website form's blocks in order by drag and drop (or arrow keys); "+" between two blocks adds a field (text, long text, email, mobile, number, date, dropdown, one / several choices, checkbox), a heading, a text, or a numbered **step** inline (the blocks under it are its section). Each block: label, placeholder, help, choices, full or half width, its answer's name; **rules**: show always / only when / except when, and required likewise, on the other answers (filled, is, contains, at least N digits, ticked...) and on the visit (a known visitor, where the form shows, the language, a tour page), all or any. Texts in every language (switch in the top bar). **Style** per variant (page, popup, tour sidebar): colours, corner radius, spacing, padding, text size. **Messages**: the thank-you texts. Live preview with the variants, a known visitor and phone size; the rules run in it as you type.
- The contact form (contact page, popup, tour sidebar) is the designer's first form: same fields, texts and look as before, its old fixed logic now rules (a known visitor's details hidden; the texting opt-ins once a mobile is typed). The browser and the server check the same rules. Answers to the form's own questions go on the CRM lead (description and Form Answers).
- The mobile field in the sidebar takes the fields' colours.
- The WhatsApp opt-in of the forms is the contact's own (WhatsApp Opt-in, on the contact; the old WhatsApp connector's field too while it is installed): with Communication Flow Designer's own WhatsApp the old field is gone. **Upgrade:** the old connector's opt-ins are copied over.
- The designer's preview: **Preview as** switches (each form type's facts: the booker's form, more riders, a bike rental, a tour page...) and **Show every block** (the blocks their rules hide now, shown faded and dashed); a click on a block of the preview opens it in the list.
- For other extensions' forms (the pre-tour forms): form types with their own blocks and rule facts (e.g. the booker's form), forms that open filled in with the answers we have, a designer opened on one form from its extension's page, the steps numbered as they show.
- **One step at a time** (Messages): customers see the steps' progress on top (number and title of each step: done, current, to come; a step done can be clicked) and Back / Next under the form, the form's own buttons on the last step; a step its rules hide is skipped; an error opens its step. Off (default): every step on one page.
- **Full preview** (Preview toolbar): the form full screen as a customer goes through it, one step at a time, desktop or phone size, a made-up answer in every field, the unsaved changes included; Esc closes it.
- Blocks with **settings of their own** (a form type's blocks, e.g. the pre-tour Fitness / Technical cards): their settings in the block's panel, linked or per part, with Reset. The form's own sections say what can be done with them (move, hide, rules), without the label field they do not use.
- Form types can add their own texts to the Messages tab (the pre-tour form's sharing messages).
- Spanish for the forms' new texts (errors, rule facts).
- **Upgrade:** creates the contact form's blocks and their Spanish. Going back to 19.0.0.1.1 brings the fixed contact form back (the designer's tables stay unused).

## 19.0.0.1.1 · 2026-10-21

- New app icon (Extensions panel).
- **Reversible: no data change.**

## 19.0.0.1.0 · 2026-10-21

- Site migration: homepage, regions, blog, SEO redirects, itineraries
