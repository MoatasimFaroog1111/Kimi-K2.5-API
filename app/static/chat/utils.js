import { MODEL_LABELS } from "./constants.js";

export function getModelLabel(model) {
  return MODEL_LABELS[model] || model || "Kimi";
}

export function getModelShortLabel(model) {
  if (!model) return "Kimi";
  if (model === "kimi-k2.7-code-highspeed") return "K2.7 Highspeed";
  if (model === "kimi-k2.7-code") return "K2.7 Code";
  if (model === "kimi-k2.6") return "K2.6";
  if (model === "kimi-k3") return "K3";
  return model;
}

export function makeConversationTitle(text) {
  const compact = String(text || "").replace(/\s+/g, " ").trim();
  return compact.length > 46 ? `${compact.slice(0, 46)}…` : compact;
}

export function formatRelativeDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "الآن";
  const diff = Date.now() - date.getTime();
  if (diff < 60_000) return "الآن";
  if (diff < 3_600_000) return `منذ ${Math.floor(diff / 60_000)} د`;
  if (diff < 86_400_000) return `منذ ${Math.floor(diff / 3_600_000)} س`;
  return new Intl.DateTimeFormat("ar-SA", { month: "short", day: "numeric" }).format(date);
}

export function sanitizeFileName(value) {
  return (value || "kimi-conversation")
    .replace(/[\\/:*?"<>|]/g, "-")
    .replace(/\s+/g, "-")
    .slice(0, 80);
}

export function makeId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `chat-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatPlainText(text) {
  return escapeHtml(text)
    .replace(/`([^`\n]+)`/g, '<code class="inline-code">$1</code>')
    .replace(/\n/g, "<br>");
}

export function formatMessageContent(text) {
  const codePattern = /```([a-zA-Z0-9_+.-]*)\r?\n([\s\S]*?)```/g;
  let html = "";
  let cursor = 0;
  let match;

  while ((match = codePattern.exec(text)) !== null) {
    html += formatPlainText(text.slice(cursor, match.index));
    const language = escapeHtml(match[1] || "code");
    const code = escapeHtml(match[2].replace(/\n$/, ""));
    html += `
      <div class="code-block">
        <div class="code-header">
          <span>${language}</span>
          <button class="copy-code" type="button">نسخ</button>
        </div>
        <pre><code>${code}</code></pre>
      </div>
    `;
    cursor = codePattern.lastIndex;
  }

  html += formatPlainText(text.slice(cursor));
  return html;
}

export async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

export function humanizeError(error, fallback) {
  if (error?.status === 401) return "مفتاح الدخول غير صحيح أو انتهت صلاحيته.";
  if (error?.status === 400) return error.message || "الطلب غير صالح.";
  if (error?.status === 429) return "تم بلوغ حد الاستخدام أو الرصيد المتاح.";
  if (error?.status === 502) return "تعذر الحصول على رد من مزود النموذج.";
  if (error?.status === 504) return "استغرق النموذج وقتًا أطول من المسموح.";
  return error?.message || fallback;
}

export async function readJson(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}
