import { readJson } from "./utils.js";

export class ChatApi {
  async configuration(key) {
    const headers = { "X-API-Key": key };
    const [healthResponse, modelsResponse] = await Promise.all([
      fetch("/health", { cache: "no-store" }),
      fetch("/models", { headers, cache: "no-store" }),
    ]);

    const modelsPayload = await readJson(modelsResponse);
    if (!modelsResponse.ok) {
      const error = new Error(modelsPayload.detail || "تعذر قراءة النماذج المتاحة.");
      error.status = modelsResponse.status;
      throw error;
    }

    const healthPayload = healthResponse.ok ? await readJson(healthResponse) : {};
    const models = Array.isArray(modelsPayload.models)
      ? modelsPayload.models.filter((model) => typeof model === "string")
      : [];

    if (!models.length) {
      throw new Error("لم تُرجع الخدمة أي نماذج متاحة.");
    }

    const defaultModel = models.includes(healthPayload.model)
      ? healthPayload.model
      : models[0];

    return { models, defaultModel };
  }

  async streamMessage({ key, message, model, history, onEvent }) {
    const response = await fetch("/chat/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": key,
      },
      body: JSON.stringify({ message, model, history }),
    });

    if (!response.ok) {
      const payload = await readJson(response);
      const error = new Error(payload.detail || `فشل الطلب برمز ${response.status}.`);
      error.status = response.status;
      throw error;
    }

    if (!response.body) {
      throw new Error("المتصفح لا يدعم قراءة الرد المتدفق.");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    const processLine = (line) => {
      const trimmed = line.trim();
      if (!trimmed) return;
      let event;
      try {
        event = JSON.parse(trimmed);
      } catch {
        throw new Error("وصلت بيانات غير صالحة من الخادم.");
      }
      onEvent(event);
    };

    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) processLine(line);
      if (done) {
        if (buffer.trim()) processLine(buffer);
        break;
      }
    }
  }
}
