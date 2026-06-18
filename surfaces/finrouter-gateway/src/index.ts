// surfaces/finrouter-gateway/src/index.ts
import Fastify from "fastify";
import cors from "@fastify/cors";
import { chat, getCostSummary } from "./gateway.js";
import { ChatRequest } from "./types.js";

const app = Fastify({ logger: true });
await app.register(cors, { origin: true });

app.get("/health", async () => ({ status: "ok" }));

app.post<{ Body: ChatRequest }>("/chat", async (request, reply) => {
  try {
    const result = await chat(request.body);
    return result;
  } catch (err: any) {
    request.log.error(err, "chat error");
    return reply.status(500).send({ error: err?.message ?? "unknown error" });
  }
});

app.get("/cost/summary", async () => getCostSummary());

const port = parseInt(process.env.PORT ?? "3001", 10);
await app.listen({ port, host: "0.0.0.0" });
console.log(`finRouter gateway listening on :${port}`);
