# Phase 1C web usability and operational workflows

## Initial audit

| Area | Existing implementation | Remaining work |
| --- | --- | --- |
| Navigation and page layout | The React shell filters the desktop sidebar by account and selected workspace. On small screens the sidebar previously wrapped above the dashboard. | Verify the new drawer across physical mobile browsers. Review crowded forms, action placement, and post-submit navigation. |
| Activity history | Farm Activity History already has an aggregate API, record details, options, filters and exports in `backend/app/activity_history.py`. The web app has a View Activities workspace. | Compare record coverage, query performance, filters, sorting and multi-record detail interactions against Phase 1C. Remove redundant embedded history only after the dedicated view covers the same operations. |
| Finance | Cash activity and export use the existing farm expense and financial data. The lender workspace also shows disbursement and repayment history. | Audit source classifications, date filters, duplicate counting, sale receipt timing, loan financing separation, and transaction detail navigation before changing totals. |
| Feed inventory | The backend stores feed products and receipts, feeding issues and adjustments in the existing feed ledger. Recommendations, schedules, and outlook already have dedicated code. | Verify catalogue sources and local availability, separate product and stock-entry screens, and confirm automatic session association and server timestamps. |
| Evidence | The web recorder uses MediaRecorder with supported WebM or MP4 formats. The evidence API validates operations, restricts access and uses the configured evidence directory. | Test live preview and supported camera controls on physical devices. Verify retry behavior, resource cleanup and private storage persistence across hosted restarts. |
| Staff | Phase 1B has scoped unit assignments, access history and a development-branch feeding-history view. Owner checks still guard operational uploads and record writes. | Finish scoped delegated writes, dedicated staff onboarding and attribution in Phase 1B before making Phase 1C forms available to staff. |

The current production database is Neon PostgreSQL. Use isolated SQLite and PostgreSQL for development tests. Keep Flutter deferred as agreed. Preserve live records and publish to Render only after approval.

## Checklist

| Item | Status |
| --- | --- |
| Mobile web drawer and compact header | Locally verified in headless Edge with a component fixture and signed-in farmer and institution workspaces. Physical-device acceptance testing pending |
| Existing desktop navigation and permission filtering | Existing navigation reused. Production build verified |
| Activity history and page simplification | Partially implemented |
| Finance transaction history and analytics | Partially implemented |
| Feed catalogue and inventory separation | Pending audit and implementation |
| Simplified feeding capture | Partially implemented |
| Camera evidence and persistent storage | Partially implemented |
| Staff permissions and operational attribution | Phase 1B dependency |
| Hosted verification and deployment | Pending |

## Mobile web acceptance checks

1. Open a signed-in workspace at desktop width and confirm the sidebar, active page, production submenu and account controls behave as before.
2. At phone width, verify the menu button opens the left drawer and the page behind it cannot scroll. Tab through drawer controls, press Escape, and confirm focus returns to the menu button.
3. Reopen and dismiss using the close button and backdrop. Choose a page and confirm the drawer closes, the title updates, and the page begins at the top.
4. Test the notification and account controls. Verify that institutional users only see their allowed navigation and that browser back and viewport resizing dismiss an open drawer.

The headless fixture passed mobile and desktop visibility, scroll locking, Escape, focus restoration, navigation, backdrop dismissal, and resize dismissal. The signed-in test passed against an isolated backend with fictional farmer and institution accounts after correcting the test origin's CORS settings. It verified mobile navigation, desktop sidebar visibility and institution permission filtering. Physical browser and device checks remain open.
