# lince.sh

Website for the [LINCE](https://github.com/RisorseArtificiali/lince) project.

Static HTML + Tailwind CDN. Hosted on GitHub Pages.

## Local preview

```bash
python3 -m http.server 8000 --directory docs
# Run from the repository root; open http://localhost:8000
```

## Deploy

The site sources live in `docs/`; the documentation app in `docs/documentation/`
uses Docsify. Changes are reviewed in the same PR as the feature. Merging to
`main` makes them available to the configured GitHub Pages deployment.

The homepage links to the [Views and Themes guide](documentation/dashboard/views-and-themes.md).
Its palette previews in `assets/dashboard-theme-*.svg` come from the dashboard
renderer; they are not screenshots of the compact or statusline layouts.

## Custom domain

The `CNAME` file points to `lince.sh`. DNS must have:
- A records pointing to GitHub Pages IPs
- Or CNAME record pointing to `risorseartificiali.github.io`
