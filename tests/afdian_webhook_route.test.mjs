import assert from "node:assert/strict";
import { test } from "node:test";
import route, { onRequest } from "../functions/afdian/webhook.js";

const payload = {
  ec: 200,
  data: {
    type: "order",
    order: {
      out_trade_no: "order1",
      user_id: "u1",
      show_amount: "5.00",
      status: 2,
    },
  },
};

function env(calls) {
  return {
    GITHUB_DISPATCH_TOKEN: "ghp_test",
    fetch: async (url, init) => {
      calls.push({ url, init });
      return new Response(null, { status: 204 });
    },
  };
}

test("pages function route handles afdian webhook posts", async () => {
  const calls = [];
  const request = new Request("https://oauth.sgscq.com/afdian/webhook", {
    method: "POST",
    body: JSON.stringify(payload),
  });

  const response = await onRequest({ request, env: env(calls) });

  assert.equal(response.status, 200);
  assert.equal(calls.length, 1);
});

test("default export supports worker-compatible fetch", async () => {
  const calls = [];
  const request = new Request("https://oauth.sgscq.com/afdian/webhook", {
    method: "POST",
    body: JSON.stringify(payload),
  });

  const response = await route.fetch(request, env(calls));

  assert.equal(response.status, 200);
  assert.equal(calls.length, 1);
});
