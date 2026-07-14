import type { Plugin } from "@opencode-ai/plugin";
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

const SKILL_CANDIDATES = [
  "ai-dlc-skill/SKILL.md",
  ".opencode/skills/ai-dlc-skill/SKILL.md",
];

export const CDHAiDLCPlugin: Plugin = async () => ({
  "experimental.chat.system.transform": async (_input, output) => {
    for (const rel of SKILL_CANDIDATES) {
      const fp = join(process.cwd(), rel);
      if (existsSync(fp)) {
        const raw = readFileSync(fp, "utf-8");
        const body = raw.replace(/^---[\s\S]*?\n---\n?/, "");
        output.system.push(
          `<!-- AI-DLC:start v=4.0.0 -->\n${body}\n<!-- AI-DLC:end -->`
        );
        break;
      }
    }
  },
});
