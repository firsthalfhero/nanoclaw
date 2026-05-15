# NanoClaw Skill Installation Guide

## Prerequisites

1. **NanoClaw skill hosting** — You must have access to an OpenRouter-hosted NanoClaw environment
2. **PostgreSQL backend running** — The nutrition tracker API must be deployed and accessible
3. **OpenRouter API key** — For vision OCR and text estimation
4. **Telegram bot** — Created via BotFather

## Installation Steps

### 1. Prepare the Skill Files

Clone or copy the nutrition tracker to your NanoClaw skills directory:

```bash
git clone <repo-url> nutrition-tracker
cd nutrition-tracker/nutri-skill
```

### 2. Configure Environment Variables

The skill requires these environment variables to be set in your NanoClaw environment:

```env
# API endpoint (where nutri-api is running)
NUTRI_API_URL=http://host.docker.internal:8000
# Or if running on remote host:
NUTRI_API_URL=http://your-host-ip:8000

# OpenRouter API key (for vision and text models)
OPENROUTER_API_KEY=sk-or-...

# Model selection
OPENROUTER_VISION_MODEL=google/gemini-3.1-flash-lite
OPENROUTER_TEXT_MODEL=google/gemini-3.1-flash-lite
```

**Note:** These must match the `.env` file in the `nutrition_tracker/` directory (compose root).

### 3. Register the Skill with NanoClaw

NanoClaw loads skills from a configured directory. Ensure `SKILL.md` is in the skill directory:

```
nutri-skill/
├── SKILL.md                (skill definition)
├── scripts/
│   ├── nutri_cli.py        (CLI executable)
│   ├── openrouter.py       (vision/text helpers)
│   └── requirements.txt     (Python dependencies)
└── tests/
```

NanoClaw will auto-discover and load `SKILL.md` when the skill is registered.

### 4. Install Python Dependencies

If running the CLI locally for testing:

```bash
cd nutri-skill/scripts
pip install -r requirements.txt
```

**In NanoClaw:** Dependencies (`httpx`, `pydantic`, `pytz`) are installed automatically during the NanoClaw container build via the Dockerfile. No manual installation is needed.

### 5. Register Commands with BotFather

Use the provided command list to register with Telegram BotFather:

```bash
# Open Telegram
# Message @BotFather with command: /setcommands
# Then paste the output of:
cat botfather_commands.txt
```

Or manually in BotFather:
```
/setcommands
nutrition_tracker
```

Then paste:
```
nutri_summary - Get today's nutrition summary
nutri_photo - OCR a nutrition label photo
nutri_log - Log a meal from a food or recipe
nutri_check_meal - View details of a meal
nutri_water - Log water intake
nutri_today - Detailed breakdown of today's meals
nutri_week - Get week summary
nutri_recipe - Manage recipes
nutri_food - Manage foods
nutri_target - View or set daily targets
nutri_edit - Edit meal macros
nutri_delete - Delete a meal
```

### 6. Test the Installation

#### Test via CLI (local)

```bash
cd nutri-skill/scripts

# Export env vars
export NUTRI_API_URL=http://localhost:8000
export OPENROUTER_API_KEY=sk-or-...

# Test a simple command
python nutri_cli.py summary

# Test with a saved food
python nutri_cli.py food list
```

#### Test via Telegram

1. Send `/nutri_summary` to your bot
2. Should receive today's nutrition summary
3. Try `/nutri_today` for detailed breakdown
4. Try `/nutri_water 500` to log water

### 7. Deploy to Docker

If deploying the full nutrition tracker:

```bash
cd nutrition_tracker
docker compose up -d
```

This starts:
- `nutri-db` (PostgreSQL)
- `nutri-api` (FastAPI on port 8000)
- `nutri-backup` (nightly pg_dump)
- `nutri-adminer` (optional database UI on port 8080, profile: tools)

### 8. Verify the Skill is Working

Check NanoClaw logs for the skill:

```bash
# In your NanoClaw environment
docker logs <nanoclawed-container>
```

Look for messages indicating skill registration and successful command routing.

---

## Troubleshooting

### "Command not found" in Telegram

**Solution:** Ensure BotFather command list is updated. Run `/setcommands` again in BotFather.

### "Could not connect to API"

**Possible causes:**
- `NUTRI_API_URL` is wrong or API is down
- Docker network issue (use `host.docker.internal` if in same Docker Compose)
- Firewall blocking the port

**Solution:**
```bash
# Test API connectivity
curl http://localhost:8000/healthz

# Check Docker network
docker network ls
docker inspect <network-name>
```

### "Vision model returned invalid JSON"

**Cause:** OpenRouter API error or rate limit

**Solution:**
- Check `OPENROUTER_API_KEY` is valid
- Check account balance at https://openrouter.ai
- Retry the command (models can be flaky)

### "Food not found"

**Cause:** Food was not created or is soft-deleted

**Solution:**
```bash
# List available foods
python nutri_cli.py food list

# Create a new food
python nutri_cli.py food add-manual "Food Name" 100 10 5 20
```

### Python dependencies error

**Solution:**
```bash
pip install --upgrade -r nutri-skill/scripts/requirements.txt
```

---

## Configuration

### Model Selection

To use a different OpenRouter model:

1. Edit `.env` (or NanoClaw environment):
   ```env
   OPENROUTER_VISION_MODEL=openai/gpt-4-vision
   OPENROUTER_TEXT_MODEL=meta-llama/llama-2-70b-chat
   ```

2. Test with:
   ```bash
   OPENROUTER_VISION_MODEL=<new-model> python nutri_cli.py photo <image.jpg>
   ```

### API URL

If the API is on a different host:

```env
NUTRI_API_URL=http://192.168.1.100:8000
```

---

## Skill File Format

The `SKILL.md` file is parsed by NanoClaw to:
1. Extract command descriptions from headers (`### /nutri-*`)
2. Route incoming Telegram messages to the appropriate CLI subcommand
3. Parse JSON responses and format as Telegram messages

Editing `SKILL.md` requires NanoClaw to reload the skill (usually automatic on save, or restart the container).

---

## Next Steps

- **Seed initial data:** Run `docker compose exec nutri-api python scripts/seed_dev.py` to create sample foods and recipes
- **Test end-to-end:** Follow the "Test via Telegram" section above
- **Set daily targets:** Use `/nutri_target set 2500` to set your calorie goal
- **Review operations:** See `docs/operations.md` for daily operations and troubleshooting

---

## Support

For issues or questions:
1. Check `docs/requirements.md` (spec)
2. Review `docs/operations.md` (runbook)
3. Check NanoClaw logs and API logs (`docker compose logs`)
4. Test CLI directly (bypass NanoClaw for isolation)

