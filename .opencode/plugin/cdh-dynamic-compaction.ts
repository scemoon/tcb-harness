import type { Plugin } from "@opencode-ai/plugin";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const MODEL_REGISTRY: Record<string, number> = {
  "anthropic/claude-sonnet-4-5":        200_000,
  "anthropic/claude-sonnet-4":          200_000,
  "anthropic/claude-haiku-4-5":         200_000,
  "anthropic/claude-opus-4-5":          200_000,
  "anthropic/claude-opus-4":            200_000,
  "anthropic/claude-3-5-sonnet-20241022": 200_000,
  "anthropic/claude-3-5-haiku-20241022":  200_000,
  "anthropic/claude-3-opus-20240229":   200_000,
  "openai/gpt-4o":                      128_000,
  "openai/gpt-4o-mini":                 128_000,
  "openai/gpt-4-1":                     1_000_000,
  "openai/gpt-4-1-mini":                1_000_000,
  "openai/gpt-4-1-nano":                1_000_000,
  "google/gemini-2.0-flash-001":        1_048_576,
  "google/gemini-2.5-pro-preview-03-25": 1_048_576,
  "deepseek/deepseek-chat":             64_000,
  "deepseek/deepseek-reasoner":         64_000,
  "meta-llama/llama-3.1-405b":          128_000,
  "mistral/mistral-large":              128_000,
  "mistral/mistral-small":              32_000,
};

const DEFAULT_CONTEXT = 128_000;
const RESERVED_RATIO = 0.25;
const RESERVED_FLOOR = 40_000;
const RESERVED_CEIL = 200_000;

function calcReserved(context: number): number {
  return Math.min(
    Math.max(Math.round(context * RESERVED_RATIO), RESERVED_FLOOR),
    RESERVED_CEIL
  );
}

function getModelContext(model: string): number {
  const entry = MODEL_REGISTRY[model];
  if (entry) return entry;
  const provider = model.split("/")[0];
  for (const [key, ctx] of Object.entries(MODEL_REGISTRY)) {
    if (key.startsWith(provider + "/")) return ctx;
  }
  return DEFAULT_CONTEXT;
}

export const CDHDynamicCompactionPlugin: Plugin = async ({ client }) => {
  const configPath = join(process.cwd(), ".opencode", "config.json");

  let applied = false;

  const apply = async (model: string) => {
    if (applied) return;
    applied = true;

    const context = getModelContext(model);
    const desired = calcReserved(context);

    try {
      const raw = readFileSync(configPath, "utf-8");
      const cfg = JSON.parse(raw);
      if (cfg.compaction?.reserved === desired) return;

      cfg.compaction = {
        auto: true,
        prune: false,
        ...cfg.compaction,
        reserved: desired,
      };
      writeFileSync(configPath, JSON.stringify(cfg, null, 2) + "\n");

      try {
        await client.config.update({
          body: { compaction: cfg.compaction } as any,
        });
      } catch {
      }
    } catch {
    }
  };

  try {
    const resp: any = await client.config.get();
    const model: string | undefined = resp.data?.model ?? resp.model;
    if (model) await apply(model);
  } catch {
  }

  return {
    config: async (input: any) => {
      if (applied) return;
      const model = input?.model ?? input?.data?.model;
      if (model) await apply(model);
    },
  };
};
