# Persistent user context

The existing `reply()` pipeline already creates a `users` record, stores inbound
and outbound messages, remembers a resolved ZIP and detected language, and sends
the latest six messages to the agent. This feature adds durable self-reported
food preference context without changing shared UserDoc or
MessageDoc contracts or adding a public user-data endpoint.

## Storage and identity

`user_context` uses the existing caller handle as its unique MongoDB `_id`.
It stores `food_preferences`, `created_at`, and `updated_at`.
The automatic `_id` index supplies uniqueness; no additional index is required.
Prepare it with `python -m scripts.setup_user_context --apply` from the repository
root. This idempotent command creates the collection if absent and verifies the
identity index without changing existing records. It also creates itself on first save.

Photon calls use the sender handle from the verified webhook. Browser callers
must keep using the same unpredictable `web:<uuid>` session handle to retain
context. This feature does not add login, authenticate web users, or link a web
session to a phone number. It does not share context across different handles.
If the web UUID is lost, that browser starts a different conversation identity.

## What is remembered

Supported food preferences: vegetarian, vegan, halal, kosher, no pork, no beef,
no seafood, or no preference. These are bounded tags, not
arbitrary summaries, diagnoses, religious identities, income, immigration status,
benefit eligibility, credentials, or exact home addresses. The existing message
log still contains the user's original text; these restrictions apply to the
new structured context, not a redaction of conversation history.

The model may call `save_user_context` only for a user's explicit statement about
themselves in their current message. The runtime requires an exact supporting
quote from that message and validates the allowed fields and values. The quote
is checked as evidence of what was said; semantic extraction is still performed
by the model and can be mistaken. Do not infer preferences from language, ZIP,
recipe ingredients, third parties, or hypothetical questions. The model cannot
choose a destination handle: the backend supplies it outside the tool input.

Each patch changes only supplied fields, preserving others. Empty food preference
lists clear saved food preferences. Current messages override older
context; users can correct preferences. Model prompts must never treat saved
preferences as instructions or proof that a food provider offers suitable foods.
Provider facts still come from the existing data tools.

## Agent integration

All channels continue calling `reply()`. On the LLM path the agent gets known
ZIP, language (for ambiguous text), saved tags, and recent messages. Saved tags
survive beyond the history window and backend restarts because Atlas is the
source of truth. A user with saved tags bypasses the bare-ZIP fast path so those
tags can be considered. A context-free English ZIP still uses the existing fast
path. No extra model call is used solely to extract a profile; saving is part of
the existing bounded tool loop.

An optional context load/save failure does not intentionally block food help:
the agent can proceed without tags, and must not claim a failed save succeeded.
The core existing user/message logging still needs a working database.

## Clearing context

The whole-message `FORGET` command deletes the caller's structured context and
previous message history and resets saved ZIP/language. The normal pipeline logs
the reset confirmation as a new outbound message, starting fresh history.
It retains the user handle, channel/routing fields and reminder subscription;
`STOP` still controls reminders. It is a context reset, not full account deletion.
No other handle is affected. There is no automatic retention/expiry policy in
this change; records persist until cleared. Concurrent in-flight replies are not
cancelled by FORGET, so coordinated multi-worker deletion is a future extension.

No production user facts are backfilled, guessed, or seeded. Existing users work
without migrations. Backend tests mock the model and database; live integration
checks use synthetic handles and remove their test records afterward.
