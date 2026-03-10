# Kevin Galim — al-folio Academic Website

This folder contains the content files for the [al-folio](https://github.com/alshedivat/al-folio) Jekyll theme.

## File Structure

```
al-folio/
├── _config.yml                   # Main site config (name, links, scholar ID, etc.)
├── Gemfile                       # Ruby dependencies
├── _pages/
│   ├── about.md                  # Landing page (profile bio, news, selected papers)
│   ├── publications.md           # Full publications list (auto-generated from .bib)
│   └── cv.md                     # CV page (links to PDF)
├── _bibliography/
│   └── papers.bib                # All publications in BibTeX format
└── _news/
    ├── 2026-01-15-iclr.md
    ├── 2026-01-15-delta-workshop.md
    ├── 2026-01-10-eacl.md
    ├── 2025-05-01-icml.md
    ├── 2025-03-01-acl-wacv.md
    └── 2024-07-01-eccv.md
```

## Quick Setup

### 1. Clone al-folio

```bash
git clone https://github.com/alshedivat/al-folio.git my-site
cd my-site
```

### 2. Copy these files into the cloned repo

```bash
cp -r al-folio/* my-site/
```

### 3. Install dependencies

```bash
bundle install
```

### 4. Add your profile photo

Place your photo at:
```
assets/img/prof_pic.jpg
```

### 5. Run locally

```bash
bundle exec jekyll serve
# → http://localhost:4000
```

### 6. Deploy to GitHub Pages

Push to a repo named `<your-username>.github.io` and enable GitHub Pages
in the repo Settings → Pages → Deploy from branch `main`.

## Key Customizations

| File | What to update |
|---|---|
| `_config.yml` | Your email, GitHub/LinkedIn/Scholar IDs, site URL |
| `_pages/about.md` | Bio text, profile photo filename |
| `_bibliography/papers.bib` | Add `arxiv = {XXXX.XXXXX}` for each paper once available |
| `_news/*.md` | Add new announcements as new `.md` files |

## Notes on papers.bib

- Papers with `selected = {true}` appear on the homepage under "Selected Publications"
- `equal_contrib = {true}` renders the * equal contribution note
- Add `html = {https://...}`, `pdf = {https://...}`, `code = {https://...}` fields for buttons
