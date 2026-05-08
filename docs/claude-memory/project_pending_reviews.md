---
name: Pending Code Reviews
description: Features that need or have completed code review
type: project
originSessionId: d463b4ac-a870-4ca6-91e4-f2b227e2688e
---
## Review A — RegimeDetector ✅ COMPLETATA (2026-05-08)

All critical bugs fixed. Remaining minor items (not blocking):
- CASO 2 + CASO 3 flow redundancy (code quality, no runtime impact)
- `asyncio.run()` in sync Celery task — acceptable for pre-market daily task

## Review C — Telegram Approval Flow ✅ COMPLETATA (2026-05-08)

All critical and important bugs fixed:
- `httpx.Client` scope extended to cover the loop (was closing before POST calls)
- `_remove_keyboard` now uses injected notifier instead of creating new instance
- `edit_message_reply_markup(keyboard=None)` now sends `"reply_markup": {}` to Telegram
- 5 failing tests fixed (AsyncMock for send_message_with_keyboard)
- Dead import and variable shadowing cleaned up

Remaining intentional behavior (documented):
- Unauthorized user tap → no `answerCallbackQuery` → 30s spinner (intentional, avoids info leak)
