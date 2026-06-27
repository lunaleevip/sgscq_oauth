const DEFAULT_REPO = "lunaleevip/sgscq_oauth";
const DISPATCH_EVENT = "afdian_order";

function text(body, status = 200) {
  return new Response(body, {
    status,
    headers: { "content-type": "text/plain; charset=utf-8" },
  });
}

function getSecret(request) {
  const url = new URL(request.url);
  return url.searchParams.get("secret") || request.headers.get("x-webhook-secret") || "";
}

function isPaidOrder(payload) {
  if (!payload || payload.ec !== 200) return false;
  if (payload.data?.type !== "order") return false;
  const order = payload.data?.order || {};
  const status = String(order.status ?? "").toLowerCase();
  return status === "2" || status === "paid" || status === "success" || status === "completed";
}

async function dispatchGithub(order, env) {
  const repo = env.GITHUB_REPO || DEFAULT_REPO;
  const fetchImpl = env.fetch || fetch;
  const body = {
    event_type: DISPATCH_EVENT,
    client_payload: {
      out_trade_no: String(order.out_trade_no || ""),
      user_id: String(order.user_id || ""),
      total_amount: String(order.total_amount || order.show_amount || ""),
      order,
    },
  };

  const response = await fetchImpl(`https://api.github.com/repos/${repo}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_DISPATCH_TOKEN}`,
      Accept: "application/vnd.github+json",
      "Content-Type": "application/json",
      "User-Agent": "sgscq-afdian-webhook",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok && response.status !== 204) {
    const message = await response.text().catch(() => "");
    throw new Error(`GitHub dispatch failed: ${response.status} ${message}`.trim());
  }
}

export async function handleRequest(request, env) {
  if (request.method !== "POST") {
    return text("method not allowed", 405);
  }
  if (env.AFDIAN_WEBHOOK_SECRET && getSecret(request) !== env.AFDIAN_WEBHOOK_SECRET) {
    return text("unauthorized", 401);
  }
  if (!env.GITHUB_DISPATCH_TOKEN) {
    return text("missing GITHUB_DISPATCH_TOKEN", 500);
  }

  let payload;
  try {
    payload = await request.json();
  } catch {
    return text("bad json", 400);
  }

  if (!isPaidOrder(payload)) {
    return text("ignored", 202);
  }

  await dispatchGithub(payload.data.order, env);
  return text("ok", 200);
}

export default {
  fetch(request, env) {
    return handleRequest(request, env);
  },
};
