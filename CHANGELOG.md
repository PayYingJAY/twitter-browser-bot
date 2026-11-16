# 2026-11-16

- Unified Doubao website and API generation under one CLI.
- Added OpenAI Chat Completions, OpenAI Responses, Anthropic Messages and Gemini generateContent adapters.
- Added local dotenv configuration, interactive setup, config validation, standalone model test and preview mode.
- Replaced fixed webpage sleeps and broad text scraping with fresh-assistant-message polling. Updated input support for the current contenteditable editor.
- Removed legacy automatic password login and template fallbacks.
- Validation: 13 unit tests passed; clean virtual-environment install and two real Coding Plan / Seed 2.1 Pro generation requests succeeded. No X likes/comments were performed.
- Initial website check was logged out; superseded by the signed-in verification below.

## Doubao signed-in verification and extraction fix

- Verified two consecutive generations in the signed-in Doubao website on 2026-11-16 using the same prompt format as the adapter.
- Fixed reply extraction: target `receive_message > ... > message_text_content` instead of the complete message wrapper, excluding action labels, timestamps and suggested follow-up questions.
- Use the answer body's `data-streaming` flag in addition to the stop control and text stability. Existing local configurations using the previous broad selector are upgraded automatically.
- First response: 太棒啦，恭喜完成第一个 Python 项目，继续加油！
- Second response: 晚霞一定超美的，在公园吹着风看晚霞想想就很舒服。
- Both answer bodies reported `data-streaming="false"`; the second answer remained separate from the first. No X likes or comments were sent.
- Scope: signed-in browser UI smoke verification plus Python adapter regression tests. A Selenium profile uses its own login state; existing user-browser sessions and Cookies are not copied or published.

- Post-fix regression: all 16 unit tests passed, including old-selector migration, assistant-body-only extraction and active-stream blocking.

## Modern free-website backend

- Default Doubao backend is now Playwright with persistent Chrome login, locator auto-waiting and one-shot multiline fill. Doubao no longer needs ChromeDriver; X still uses Selenium.
- Supports installed Chrome/Edge or explicitly installed Playwright Chromium. Existing local configurations select the new default, while `doubao.backend=selenium` remains an explicit legacy option.
- Browser profile remains local in `browser_data/doubao`; no personal-browser Cookies are extracted or published.
- All 22 tests passed, including three actual headless Chrome integration tests against a local HTML fixture. These execute the new Python adapter and cover consecutive replies, stream completion, multiline prompts, metadata exclusion and timeout/no-resend behavior.
- Earlier signed-in Doubao UI checks apply to the page selectors and prompt format. The new persistent-profile live generation check is tracked separately below.

- Live verification status for the new Playwright-owned profile: awaiting first login; authenticated generation in this profile has not yet been confirmed. The Selenium fallback remains available.
