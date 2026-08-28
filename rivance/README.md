# Rivance site

Plain HTML/CSS/JS, mobile-first, no build step. Open any `.html` file directly or serve the folder with any static file server.

```
rivance/
  index.html       homepage
  frontdesk.html    product page (pricing, FAQ)
  about.html        about Rivance
  contact.html       contact form + channels
  css/style.css      shared design system
  js/main.js         mobile nav toggle + contact form handler
```

## Before this goes live

Contact details and pricing are real (confirmed 2026-08-28):

- WhatsApp: `+27 64 683 3903`
- Email: `rivance@gmail.com`
- Pricing: Essential R6,500 setup / R3,500 per month; Complete R9,000 setup (R4,500 for the first 3 founding clients) / R5,250 per month; Practice Pro R14,500 setup / R9,500 per month

**Still a placeholder — confirm before launch:**

| Placeholder | Used for | Files |
|---|---|---|
| "Johannesburg, South Africa" | Footer, contact page | all pages |

**The founding-client discount on Complete is a first-3-clients offer.** Once those 3 slots are taken, remove the struck-through `R9,000` / `R4,500` price and the "first 3 founding clients" line in `frontdesk.html`'s pricing section and just show `R9,000` as the setup fee.

**Contact form**: `contact.html` currently opens the visitor's email client via a `mailto:` link built in `js/main.js` (see the `contact-form` submit handler) — nothing is sent automatically, and nothing is stored. For a real submission flow (spam handling, a database record, a Slack/email notification), wire the form to a backend or a service like Formspree and update the `submit` handler accordingly.

**Founder/team content**: `about.html` describes Rivance in the collective ("a small team of engineers") rather than naming individuals, since no real founder bios were provided. Personalize with real names/photos if wanted.

## Design system

See the comment block at the top of `css/style.css` for the palette and typography rationale. Design tokens are CSS custom properties on `:root` — change colors/fonts there rather than hunting through individual rules.
