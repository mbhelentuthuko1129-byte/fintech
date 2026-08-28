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

**Placeholder values to replace** (search for these strings across all `.html` files):

| Placeholder | Used for | Files |
|---|---|---|
| `+27 82 000 0000` / `27820000000` | WhatsApp CTA links, footer, contact page | all pages |
| `hello@rivance.co.za` | Email links, contact form destination | all pages |
| `R990`, `R1,890`, tier names/features | Pricing table | `frontdesk.html` |
| "Johannesburg, South Africa" | Footer, contact page | all pages |

**Contact form**: `contact.html` currently opens the visitor's email client via a `mailto:` link built in `js/main.js` (see the `contact-form` submit handler) — nothing is sent automatically, and nothing is stored. For a real submission flow (spam handling, a database record, a Slack/email notification), wire the form to a backend or a service like Formspree and update the `submit` handler accordingly.

**Founder/team content**: `about.html` describes Rivance in the collective ("a small team of engineers") rather than naming individuals, since no real founder bios were provided. Personalize with real names/photos if wanted.

## Design system

See the comment block at the top of `css/style.css` for the palette and typography rationale. Design tokens are CSS custom properties on `:root` — change colors/fonts there rather than hunting through individual rules.
