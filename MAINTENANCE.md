# Space Maintenance Notes

Operational housekeeping for the running Space. Run these from a terminal in the
Space (Dev Mode), or from the integrated terminal in VS Code-for-web attached to
the Space.

---

## Removing a credential that was entered into the Hermes setup by mistake

If a key was typed into Hermes' own setup/provider config when it should only live
as a **Space secret** (Settings → Variables and secrets), pull it back out of
Hermes so the only copy is the Space secret. Hermes keeps its state under
`HERMES_HOME=/data/.hermes` (persists across rebuilds).

1. **Find where it landed.** Search Hermes' own files only:
   ```bash
   grep -rIn "FAL_KEY\|fal" /data/.hermes/ 2>/dev/null
   ```
   The usual spots are `/data/.hermes/.env` and `/data/.hermes/config.yaml`
   (a provider/model entry or an `mcp_servers.*.env` block).

2. **Remove the line from the secrets file:**
   ```bash
   sed -i '/FAL_KEY/d' /data/.hermes/.env
   ```

3. **If it was added to `config.yaml`** (e.g. under a provider or MCP server
   `env:`), open it and delete just that key/value:
   ```bash
   ${EDITOR:-nano} /data/.hermes/config.yaml
   ```

4. **Restart Hermes** so it reloads config without the key (restart the Space, or
   restart the Hermes process/session you have running).

5. **Verify it's gone** — this should print nothing:
   ```bash
   grep -rIn "FAL_KEY" /data/.hermes/ 2>/dev/null && echo "STILL PRESENT" || echo "clean"
   ```

> The pipeline reads this key from `config.FAL_KEY`, which is sourced from the
> **Space secret** `FAL_KEY` — so keep that one in place; only the copy inside
> `/data/.hermes` is the one to remove.
