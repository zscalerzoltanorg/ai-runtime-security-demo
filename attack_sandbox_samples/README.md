# Attack Sandbox Samples

These files are intentionally designed for **defensive testing and learning** in this local demo app.

Use cases:
- Prompt injection detection
- Multi-turn instruction override testing
- Suspicious URL triage behavior
- Multimodal (image + text attachment) safety checks

Notes:
- URLs in these samples use non-production example-style domains.
- Do not use these artifacts for offensive activity.
- For multimodal tests, compare `cat_benign.png` vs `cat_adversarial.png`.
- The adversarial PNG uses metadata-based hidden prompt content while remaining visually near-identical.

Recommended demo flow:
1. Enable Zscaler AI Guard.
2. Open Prompt Presets -> Attack Sandbox (Learning).
3. Use the matching attachment file from this folder when the preset hint mentions one.
