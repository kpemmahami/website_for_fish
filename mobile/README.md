# AquaFarm Manager Mobile

Android-first Flutter application for farm records, production operations, evidence capture, and offline synchronization.

## Run locally

Start the FastAPI backend on port `8000`, then from this directory run:

```powershell
flutter pub get
flutter run
```

The app's default API address is `http://10.0.2.2:8000`, which reaches the host computer from an Android emulator. For a physical phone, open **Settings** in the app and enter the backend computer's reachable LAN address, for example `http://192.168.1.20:8000`. The phone and computer must be on the same network, and the backend firewall must allow the connection. Use HTTPS for deployments; debug Android builds allow cleartext HTTP for local development only.

## Build and verify

```powershell
flutter analyze
flutter test
flutter build apk --debug
```

The debug APK is written to `build\app\outputs\flutter-apk\app-debug.apk`.

## Current scope

The MVP supports registration and login, farm and production-unit setup, stocking, feeding, mortality, sampling, water-quality entries, dashboard/report views, and offline queuing with retry. Operational submissions require a newly captured 15-second video and GPS; evidence is uploaded before the operation is submitted.

This is not yet a complete production release: sales and expense entry, loan servicing, exportable mobile reports, device/emulator acceptance testing, and production HTTPS deployment remain outstanding. Offline queued operations sync only when connectivity and valid backend authentication are available. Android SDK license acceptance, when required by Flutter tooling, must be performed by the developer.
