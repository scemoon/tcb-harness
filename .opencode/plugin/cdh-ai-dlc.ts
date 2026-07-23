import type { Plugin } from "@opencode-ai/plugin";
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

const CANDIDATES = [
  ".opencode/skills/ai-dlc-skill/SKILL.md",
  "ai-dlc-skill/SKILL.md",
];

const MAX_BODY_CHARS = 2500;

export const CDHAiDLCPlugin: Plugin = async () => ({
  "experimental.chat.system.transform": async (_input, output) => {
    for (const rel of CANDIDATES) {
      const fp = join(process.cwd(), rel);
      if (existsSync(fp)) {
        const raw = readFileSync(fp, "utf-8");
        let body = raw.replace(/^---[\s\S]*?\n---\n?/, "");
        if (body.length > MAX_BODY_CHARS) {
          body = body.slice(0, MAX_BODY_CHARS) +
            "\n\n... [AI-DLC skill truncated. Use `cdh aidlc` for full lifecycle.]";
        }
        output.system.push(
          `<!-- AI-DLC:start v=4.0.0 -->\n${body}\n<!-- AI-DLC:end -->`
        );
        break;
      }
    }
  },
});
