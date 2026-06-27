import worker from "../../tools/afdian_webhook_dispatch_worker.mjs";

export function onRequest(context) {
  return worker.fetch(context.request, context.env || {});
}

export default {
  fetch(request, env) {
    return worker.fetch(request, env || {});
  },
};
