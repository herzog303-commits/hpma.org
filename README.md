# Hartstene Pointe Maintenance Association website

A fast, static website for [hpma.org](https://hpma.org). No PHP, no database, no
login system. Just plain HTML, CSS and a little JavaScript. It can be hosted on
GitHub Pages (current plan) or any static host.

## Structure

```
/index.html              Homepage
/about/                  About the Pointe, Our Place, History
/governance/             Governance, Committees, Governing Documents
/amenities/              Amenities overview + 10 amenity pages
/community/              Community life & activities
/photos/                 Photo gallery (click-to-enlarge lightbox)
/contact/                Contact information
/404.html                Friendly "page not found"
/assets/
   css/site.css          All styling (design system + components)
   js/site.js            Mobile nav + gallery lightbox
   img/                  Images (hero, amenities, gallery, page images)
   docs/                 PDF documents (Bylaws, CC&Rs, maps, etc.)
/_original-site/         ARCHIVE of the old hpma.org content (see note below)
```

## Editing the site

Every page is a plain `.html` file you can open and edit directly. The site
header (navigation) and footer are repeated on each page. If you change a menu
item, update it on each page, or re-run the generator (below).

### Optional: the page generator

The interior pages were produced by a small Python script (`_tools/build.py`,
not published to the live site) so the shared header and footer stay identical
everywhere. To change the nav or footer for the whole site, edit that script's
`NAV` / `HEAD` / `FOOT` templates and re-run:

```
python _tools/build.py
```

It writes plain HTML, and there is **no build step required to host the site**. The
generator is a convenience, not a dependency.

### Adding a news item

The homepage "Good to know" section holds short, evergreen notes. Edit the
`<article class="ni">` blocks in `index.html` to update them.

### Adding photos

Drop image files into `assets/img/gallery/` and add a matching `<a>…<img></a>`
line to `photos/index.html` (or re-run the generator, which lists that folder
automatically).

## Design

Colors, typography (Hanken Grotesk) and components all live in
`assets/css/site.css` as CSS variables at the top of the file. Change a value
there and it updates everywhere.

## Owner Portal

The only owner/member destination is **Condo Control**
(`https://app.condocontrol.com/login`), linked as "Owner Portal." There are no
member-login, registration, or admin pages on this site by design.

## The `_original-site/` archive

This folder is a complete snapshot of the **public** pages, images and documents
from the previous hpma.org site, captured during the rebuild. It is kept **on the
local machine for reference only** and is git-ignored (see `.gitignore`), so it is
not pushed to GitHub or published. It is safe to delete once you're confident
everything has been carried over. To version-control it too, remove the
`/_original-site/` line from `.gitignore`.

## Hosting on GitHub Pages

1. Push this repository to GitHub (already connected to
   `github.com/herzog303-commits/hpma.org`).
2. In the repo's **Settings → Pages**, set the source to the `main` branch,
   root folder.
3. To use the custom domain `hpma.org`, add a `CNAME` file containing `hpma.org`
   and point the domain's DNS at GitHub Pages.
