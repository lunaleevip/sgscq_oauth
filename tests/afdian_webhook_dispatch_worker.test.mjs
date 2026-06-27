import assert from "node:assert/strict";
import { test } from "node:test";
import { handleRequest } from "../tools/afdian_webhook_dispatch_worker.mjs";

const paidOrderPayload = {
  ec: 200,
  em: "ok",
  data: {
    type: "order",
    order: {
      out_trade_no: "202106232138371083454010626",
      user_id: "adf397fe8374811eaacee52540025c377",
      show_amount: "5.00",
      status: 2,
    },
  },
};

function env(fetchCalls) {
  return {
    GITHUB_DISPATCH_TOKEN: "ghp_test",
    fetch: async (url, init) => {
      fetchCalls.push({ url, init });
      return new Response(null, { status: 204 });
    },
  };
}

test("dispatches paid afdian orders to the oauth snapshot repo", async () => {
  const calls = [];
  const request = new Request("https://example.com/afdian/webhook", {
    method: "POST",
    body: JSON.stringify(paidOrderPayload),
  });

  const response = await handleRequest(request, env(calls));

  assert.equal(response.status, 200);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://api.github.com/repos/lunaleevip/sgscq_oauth/dispatches");
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.headers.Authorization, "Bearer ghp_test");
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    event_type: "afdian_order",
    client_payload: {
      out_trade_no: "202106232138371083454010626",
      user_id: "adf397fe8374811eaacee52540025c377",
      total_amount: "5.00",
      order: paidOrderPayload.data.order,
    },
  });
});

test("accepts webhook secret from request header", async () => {
  const calls = [];
  const request = new Request("https://example.com/afdian/webhook", {
    method: "POST",
    headers: { "x-webhook-secret": "secret123" },
    body: JSON.stringify(paidOrderPayload),
  });
  const secureEnv = env(calls);
  secureEnv.AFDIAN_WEBHOOK_SECRET = "secret123";

  const response = await handleRequest(request, secureEnv);

  assert.equal(response.status, 200);
  assert.equal(calls.length, 1);
});

test("rejects requests with missing or wrong secret when configured", async () => {
  const calls = [];
  const request = new Request("https://example.com/afdian/webhook", {
    method: "POST",
    body: JSON.stringify(paidOrderPayload),
  });
  const secureEnv = env(calls);
  secureEnv.AFDIAN_WEBHOOK_SECRET = "secret123";

  const response = await handleRequest(request, secureEnv);

  assert.equal(response.status, 401);
  assert.equal(calls.length, 0);
});

test("ignores unpaid orders without dispatching", async () => {
  const calls = [];
  const payload = structuredClone(paidOrderPayload);
  payload.data.order.status = 1;
  const request = new Request("https://example.com/afdian/webhook", {
    method: "POST",
    body: JSON.stringify(payload),
  });

  const response = await handleRequest(request, env(calls));

  assert.equal(response.status, 202);
  assert.equal(await response.text(), "ignored");
  assert.equal(calls.length, 0);
});

test("returns an error when GitHub token is not configured", async () => {
  const calls = [];
  const request = new Request("https://example.com/afdian/webhook", {
    method: "POST",
    body: JSON.stringify(paidOrderPayload),
  });
  const missingTokenEnv = env(calls);
  delete missingTokenEnv.GITHUB_DISPATCH_TOKEN;

  const response = await handleRequest(request, missingTokenEnv);

  assert.equal(response.status, 500);
  assert.equal(await response.text(), "missing GITHUB_DISPATCH_TOKEN");
  assert.equal(calls.length, 0);
});
