# 2026-11-16

- Unified Doubao website and API generation under one CLI.
- Added OpenAI Chat Completions, OpenAI Responses, Anthropic Messages and Gemini generateContent adapters.
- Added local dotenv configuration, interactive setup, config validation, standalone model test and preview mode.
- Replaced fixed webpage sleeps and broad text scraping with fresh-assistant-message polling. Updated input support for the current contenteditable editor.
- Removed legacy automatic password login and template fallbacks.
- Validation: 13 unit tests passed; clean virtual-environment install and two real Coding Plan / Seed 2.1 Pro generation requests succeeded. No X likes/comments were performed.
- Website limitation: the inspected Doubao browser was logged out; current input markup was verified, but a signed-in end-to-end reply remains unverified. Selectors are configurable.
