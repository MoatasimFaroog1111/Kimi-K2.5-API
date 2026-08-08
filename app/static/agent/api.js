const SESSION_KEY = "kimi_gateway_key_session_v1";
const REMEMBERED_KEY = "kimi_gateway_key_local_v1";

export class AgentApi {
  getGatewayKey() {
    return sessionStorage.getItem(SESSION_KEY)
      || localStorage.getItem(REMEMBERED_KEY)
      || "";
  }

  async status() {
    return this.#jsonRequest("/agent/status", { method: "GET" });
  }

  async streamTask(payload, onEvent) {
    const response = await fetch("/agent/stream", {
      method: "POST",
      headers: this.#headers(true),
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw await this.#responseError(response);
    }
    if (!response.body) {
      throw new Error("المتصفح لا يدعم قراءة بث الوكيل.");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        this.#consumeLine(line, onEvent);
      }
      if (done) {
        if (buffer.trim()) this.#consumeLine(buffer, onEvent);
        break;
      }
    }
  }

  approve(proposalId) {
    return this.#jsonRequest(`/agent/proposals/${proposalId}/approve`, {
      method: "POST",
    });
  }

  reject(proposalId) {
    return this.#jsonRequest(`/agent/proposals/${proposalId}/reject`, {
      method: "POST",
    });
  }

  undo(proposalId) {
    return this.#jsonRequest(`/agent/proposals/${proposalId}/undo`, {
      method: "POST",
    });
  }

  ci(proposalId) {
    return this.#jsonRequest(`/agent/proposals/${proposalId}/ci`, {
      method: "GET",
    });
  }

  async #jsonRequest(url, options) {
    const response = await fetch(url, {
      ...options,
      headers: this.#headers(false),
      cache: "no-store",
    });
    if (!response.ok) {
      throw await this.#responseError(response);
    }
    return response.json();
  }

  #headers(withContentType) {
    const key = this.getGatewayKey();
    if (!key) {
      const error = new Error("أدخل مفتاح البوابة أولًا.");
      error.status = 401;
      throw error;
    }
    return {
      ...(withContentType ? { "Content-Type": "application/json" } : {}),
      "X-API-Key": key,
    };
  }

  #consumeLine(line, onEvent) {
    const trimmed = line.trim();
    if (!trimmed) return;
    let event;
    try {
      event = JSON.parse(trimmed);
    } catch {
      throw new Error("وصلت بيانات غير صالحة من الوكيل.");
    }
    onEvent(event);
    if (event.type === "error") {
      throw new Error(event.detail || "حدث خطأ داخل الوكيل.");
    }
  }

  async #responseError(response) {
    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    const error = new Error(payload.detail || `فشل الطلب برمز ${response.status}.`);
    error.status = response.status;
    return error;
  }
}
