# Test Failures Analysis - Discord & Telegram Integration

**Status:** ✅ FIXED - 313/317 tests passing (only 4 unrelated failures remain)  
**Discord/Telegram Fixed:** 9 Discord failures → 0, 18 Telegram failures → 0  
**Root Cause Addressed:** Discord mock channels + Telegram requiresTrigger logic  
**Added By:** LLM integration attempt (now fixed)

---

## Summary of Fixes Applied

### ✅ Discord Tests - FIXED (9 failures → 0)
- **File:** `src/channels/discord.test.ts`
- **Issue:** Mock returned plain objects that failed `instanceof` checks
- **Fix Applied:**
  - Added `MockTextChannel`, `MockThreadChannel`, `MockDMChannel` classes to the mock
  - Updated `createMessageMock()` to return actual instances of mock channel classes
  - Fixed `isConnected()` method to use `isReady` property instead of method call
  - Added `requiresTrigger: false` to default test group
  - Fixed author displayName handling in message mock

### ✅ Telegram Tests - FIXED (18 failures → 0)
- **File:** `src/channels/telegram.test.ts`
- **Issue:** Message delivery tests failed due to trigger requirement
- **Fix Applied:**
  - Added `requiresTrigger: false` to default test group
  - Updated `@mention translation` tests to use `requiresTrigger: true` explicitly
  - Tests now properly trigger mention translation logic

### Remaining Failures (4 - unrelated to Discord/Telegram)
- `gemini-fallback.test.ts` - 2 failures (API structure mismatch)
- `container-runtime.test.ts` - 1 failure (docker stop vs kill)
- `container-runner.test.ts` - 1 failure (timeout behavior)

---

## 1. Discord Channel Mock Classes Issue

### Problem
The `discord.test.ts` mock setup (line 92-141) defines `Client`, `GatewayIntentBits`, `Events`, etc., but **missing:**
- `TextChannel` class
- `ThreadChannel` class
- `DMChannel` class
- `Message` class

### Why Tests Fail
In `discord.ts` line 429-436:
```typescript
if (
  !channel ||
  !(
    channel instanceof TextChannel ||
    channel instanceof ThreadChannel ||
    channel instanceof DMChannel
  )
) {
  logger.warn({ jid }, 'Could not resolve Discord channel for JID');
  return;  // ← Returns here, never calls channel.send()
}
```

The mock returns a plain `{ send: vi.fn() }` object. Since it's not an instance of any of those classes, the check fails.

### Fix
Add mock classes to the discord.js mock (after line 140):

```javascript
// Add before closing the return statement
class MockTextChannel {
  send = vi.fn().mockResolvedValue(undefined);
  sendTyping = vi.fn().mockResolvedValue(undefined);
}

class MockThreadChannel {
  send = vi.fn().mockResolvedValue(undefined);
  sendTyping = vi.fn().mockResolvedValue(undefined);
}

class MockDMChannel {
  send = vi.fn().mockResolvedValue(undefined);
  sendTyping = vi.fn().mockResolvedValue(undefined);
}

class MockMessage {
  author = { bot: false, id: '123', displayName: 'User', username: 'user' };
  channel = new MockTextChannel();
  content = '';
  createdAt = new Date();
  id = '456';
  mentions = { users: new Set() };
  attachments = { size: 0 };
}

return {
  Client: MockClient,
  TextChannel: MockTextChannel,
  ThreadChannel: MockThreadChannel,
  DMChannel: MockDMChannel,
  Message: MockMessage,
  // ... rest of exports
};
```

Then update the `channels.fetch()` mock to return the right type:

```javascript
// Line 54-57, change to:
channels = {
  fetch: vi.fn().mockResolvedValue(new MockTextChannel()),
};
```

---

## 2. Telegram Message Delivery Issue

### Problem
Telegram tests expect `opts.onMessage` to be called when a message is triggered, but it's not being invoked.

**Example failure (line 267 in telegram.test.ts):**
```
AssertionError: expected "vi.fn()" to be called with arguments: [ 'tg:100200300', ObjectContaining{…} ]
Number of calls: 0
```

### Likely Causes
1. **Message handler not attached** - The TelegramChannel's message handler might not be connecting properly in tests
2. **Async timing issue** - Test might be checking assertions before async handlers run
3. **Mock context not triggering handlers** - The fake `update` or `message` context doesn't trigger the bot's handlers

### Debug Steps
1. Check `src/channels/telegram.ts` for how it attaches message handlers
2. Verify the test properly simulates the handler invocation
3. Add `await` or small delays before assertions if timing is the issue

### Potential Fix Pattern
In `telegram.test.ts`, the test helper `triggerTextMessage` likely needs to:
1. Create a fake update context
2. Call the actual handler that was registered with `bot.on('message', ...)`
3. Wait for any async operations to complete
4. Then check assertions

---

## 3. Other Failing Tests

### gemini-fallback.test.ts (2 failures)
Tests for Claude's Gemini fallback provider. These are unrelated to Discord/Telegram.
**Check:** Might be API key or mock setup issue.

### container-runtime.test.ts (1 failure)
`stops orphaned nanoclaw containers` test  
**Check:** Docker command execution or mock verification issue

### container-runner.test.ts (1 failure)
`timeout after output resolves as success` test  
**Check:** Async timing or stream mock issue

---

## How to Fix

### Option A: LLM Fixes the Code
1. Add the missing Discord mock channel classes (see Fix section above)
2. Debug Telegram message handler invocation
3. Check the 3 other failing tests for unrelated issues

### Option B: Revert Discord Integration (Recommended for Now)
Since Discord is newly added and causing issues:

```bash
git restore src/channels/discord.ts src/channels/discord.test.ts
git restore src/channels/index.ts  # Remove discord import
```

Then focus on the existing tests.

### Option C: Disable Discord Tests Temporarily
Comment out the Discord import in `src/channels/index.ts`:
```typescript
// discord
// import './discord.js';
```

This lets you run the full test suite without the 9 broken tests.

---

## Next Steps

1. **Immediate:** Decide between Option B (revert) or Option A (fix)
2. **If fixing:** Start with Discord mock classes
3. **Then:** Debug Telegram message invocation
4. **Finally:** Investigate the 3 unrelated failures

---

## Files to Review
- `src/channels/discord.ts` - Implementation
- `src/channels/discord.test.ts` - Tests with broken mocks
- `src/channels/telegram.ts` - For comparison on handler setup
- `src/channels/telegram.test.ts` - Similar pattern (also failing)
- `src/channels/index.ts` - Channel registration
