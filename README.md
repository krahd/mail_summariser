# Mail Summariser for macOS

Starter project for a native macOS GUI with a Python backend.

## Structure

- `macos-app/`: SwiftUI source files for the native macOS app
- `backend/`: FastAPI backend with persisted settings, logs, jobs, and undo history

## Backend quick start

```bash
cd backend
./start_backend
```

Then visit:
- `http://127.0.0.1:8766/docs`

## macOS app quick start

Open `MailSummariser.xcodeproj` in Xcode and run the `MailSummariser` scheme.

The app defaults to the backend at `http://127.0.0.1:8766`.

## Notes

This is an MVP scaffold.

Current backend behavior:
- stores settings in SQLite
- stores summary jobs in SQLite
- stores logs in SQLite
- supports a basic undo stack
- uses **demo mail data** instead of real IMAP

Next step after this scaffold:
- implement real IMAP search in `backend/mail_service.py`
- implement real LLM summary generation in `backend/summary_service.py`
- wire MailMate-specific send/compose helpers if desired
