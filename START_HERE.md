# START HERE (simple steps)

You do NOT write code. Cursor writes it. You paste prompts in order and check results.

## A. Install once (all free)
1. Cursor: https://cursor.com
2. Git: https://git-scm.com
3. Docker Desktop: https://www.docker.com/products/docker-desktop
4. Python 3.12 and uv: https://docs.astral.sh/uv/
5. Node.js (LTS): https://nodejs.org

## B. Open the project
1. Unzip this folder.
2. Open Cursor > File > Open Folder > choose `label-lag-radar`.
3. Open the terminal in Cursor and run:
   git init
   git add -A
   git commit -m "starter kit"

## C. Build, one step at a time
Open the `prompts/` folder. The files are numbered. Do them in order.

1. Open `prompts/00_MASTER_PROMPT.md`. Open a new Cursor chat (Agent mode). Paste the text between the lines. Send.
2. Open `prompts/01_PHASE_0_scaffold.md`. Open a NEW chat. Paste. Send.
3. When Cursor says the checks pass, test it, then commit (the file tells you the command).
4. Repeat with `02_PHASE_1...`, `03_PHASE_2...` and so on. New chat each time.

If Cursor shows an error: copy the error and paste it back into the same chat. Say: fix this.

## D. Accounts (create later, when a phase needs them, all free)
- Supabase (database): needed at Phase 1. Copy keys into `backend/.env` (copy `.env.example` to `.env`).
- Google AI Studio and Groq (free LLM keys): needed at Phase 3.
- LangSmith (tracing): needed at Phase 4.
- Render and Cloudflare Pages (hosting): needed at Phase 10.

## E. Never do this
- Never paste all prompts at once.
- Never commit your real `.env` file (it is already in .gitignore).
- Never skip the check after Phase 2: open some parsed labels and compare with dailymed.nlm.nih.gov.

## F. Short on time? Do only phases 0 to 5 and the dashboard from Phase 7.
