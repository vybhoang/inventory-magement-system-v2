# Amal's Boutique — Admin Console

A single-page admin dashboard for a small clothing boutique: products, suppliers, purchase orders, users/permissions, reports, and settings, with a built-in language switcher (English, Somali, Vietnamese, Chinese).

This started as a rebuild of a PHP/MySQL inventory management system and was redesigned as a self-contained static app: no server, no database setup, just open `index.html`.

## Live demo

**[inventory-magement-system-v2.vercel.app](https://inventory-magement-system-v2.vercel.app/)**

Sign in with any email/password combination (see "Running it" below). Deployed on Vercel, auto-redeploying on every push to `main`.

## Features

- **Products**: add, edit, delete products across 6 categories and standard sizes (XS-XXL)
- **Suppliers**: manage supplier records and which products they provide
- **Purchase Orders**: create orders grouped by batch, track quantities ordered vs. received
- **Users & Permissions**: role-based access across 7 permission modules (Dashboard, Reports, Purchase Orders, Products, Suppliers, Users, Point of Sale)
- **Reports**: export products, suppliers, deliveries, and purchase orders (Excel/PDF links)
- **Settings**: low stock / overstock thresholds and notification preferences
- **Multi-language**: English, Somali, Vietnamese, Chinese, dictionary-based with automatic fallback to English for any untranslated string

## Technologies used

- HTML, CSS, and vanilla JavaScript in a single file
- `localStorage` for data persistence (see "Where the data lives" below)
- Chart.js (loaded from CDN) for the dashboard charts

## Running it

No install, build step, or server needed. Download `index.html` and open it directly in a browser, or serve it from any static file host.

Demo login: any email/password combination works (this is a front-end-only demo, there's no real authentication backend).

## Where the data lives

All data (products, suppliers, orders, users, settings, and the selected language) is stored in the browser's `localStorage`, under keys prefixed `amals_` (for example `amals_products`, `amals_suppliers`). On first run, with nothing stored yet, the app seeds itself with a sample dataset. Every add, edit, or delete writes straight back to `localStorage`.

This means:
- Data persists only in that one browser, on that one device.
- Clearing browser data/cache resets everything back to the seeded sample data.
- Nothing is shared across users or devices, since there's no backend or database.

## Related project: data integrity case study

The `data-integrity-project/` folder is a separate companion project: a Python/SQL pipeline that generates realistic messy multi-source retail data, audits it for integrity issues, and consolidates it into a single master catalog. See `data-integrity-project/DATA_INTEGRITY_REPORT.md` for the full write-up.

The app itself has a "Data Quality Study" page (under Analytics in the sidebar) that surfaces this project's results directly: the before/after numbers, the method, and a searchable, paginated table of all 7,986 centralized records with a "flagged records" filter.
