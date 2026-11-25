# AquaFarm Manager Mobile

Android-first Flutter application for farm records, production operations, evidence capture, and offline synchronization.

## Run locally

Start the FastAPI backend on port `8000`, then from this directory run:

```powershell
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

The app defaults to the live HTTPS AquaFarm backend. The command above selects a local backend from an Android emulator. On a physical phone, open **Settings** to use a reachable LAN address for debug testing. Changing the address signs out the current session. Debug Android builds allow cleartext HTTP for local development.

## Build and verify

```powershell
flutter analyze
flutter test
flutter build apk --debug
```

The debug APK is written to `build\app\outputs\flutter-apk\app-debug.apk`.

## Current scope

The farmer app supports registration, approval status, email or phone sign-in, email recovery requests, saved-phone SMS verification, and a read-only assigned-units list. Password reset links open in the browser. It also supports farm and production-unit setup, stocking, feeding, mortality, sampling, water-quality entries, dashboards, reports, and offline queuing with retry. Operational submissions require a newly captured 15-second video and GPS. The app uploads evidence before submitting the operation.

After the backend deploys migration `0039_staff_feeding_access`, staff with feeding permission can open **Assigned production units**, choose the assigned unit, and record unscheduled feeding with GPS and video evidence. The app needs an internet connection to load the permitted cycles and feed products. The submission can queue on that device if connectivity drops.

Scheduled staff feeding, other delegated staff operations, sales and expense entry, loan servicing, mobile report exports, and device acceptance testing remain outstanding. Offline queued operations sync when connectivity and valid backend authentication are available. Android SDK license acceptance, when required by Flutter tooling, must be performed by the developer.
