import { QUICK_PROMPTS } from "../constants.js";
import { copyText, escapeHtml, formatMessageContent } from "../utils.js";

export class MessagesComponent {
  constructor(root, toast) {
    this.root = root;
    this.toast = toast;
    this.onPrompt = null;
  }

  bind({ onPrompt }) {
    this.onPrompt = onPrompt;
  }

  render(conversation, isSending, modelLabel = "Kimi") {
    this.root.replaceChildren();

    if (!conversation || !conversation.messages.length) {
      this.#renderWelcome(modelLabel);
      return;
    }

    const fragment = document.createDocumentFragment();
    for (const message of conversation.messages) {
      fragment.appendChild(this.#buildMessage(message, isSending));
    }
    this.root.appendChild(fragment);
    this.#attachCopyHandlers();
  }

  scrollToBottom(smooth = false) {
    window.requestAnimationFrame(() => {
      this.root.scrollTo({
        top: this.root.scrollHeight,
        behavior: smooth ? "smooth" : "auto",
      });
    });
  }

  #renderWelcome(modelLabel) {
    const welcome = document.createElement("div");
    welcome.className = "kimi-welcome";
    const chips = QUICK_PROMPTS.map((item) => `
      <button type="button" class="quick-prompt" data-prompt="${escapeHtml(item.prompt)}">
        ${escapeHtml(item.label)}
      </button>
    `).join("");

    welcome.innerHTML = `
      <div class="kimi-welcome-mark" aria-hidden="true">K</div>
      <h1>مرحبًا، أنا Kimi</h1>
      <p>ما الذي يمكنني مساعدتك في بنائه اليوم؟</p>
      <div class="welcome-model">${escapeHtml(modelLabel)}</div>
      <div class="quick-prompts">${chips}</div>
    `;

    welcome.querySelectorAll("[data-prompt]").forEach((button) => {
      button.addEventListener("click", () => this.onPrompt?.(button.dataset.prompt || ""));
    });
    this.root.appendChild(welcome);
  }

  #buildMessage(message, isSending) {
    const row = document.createElement("article");
    row.className = `message-row ${message.role}`;
    row.dataset.rawContent = message.content;

    const body = document.createElement("div");
    body.className = "message-body";

    if (message.role === "assistant") {
      const brand = document.createElement("div");
      brand.className = "assistant-mark";
      brand.textContent = "K";
      row.appendChild(brand);
    }

    const meta = document.createElement("div");
    meta.className = "message-meta";
    meta.innerHTML = `
      <span>${message.role === "user" ? "أنت" : "Kimi"}</span>
      <button class="copy-message" type="button" aria-label="نسخ الرسالة">نسخ</button>
    `;

    const content = document.createElement("div");
    content.className = "message-content";
    if (message.role === "assistant" && !message.content && isSending) {
      content.innerHTML = '<div class="typing-line"><span></span><span></span><span></span></div>';
    } else {
      content.innerHTML = formatMessageContent(message.content || "");
    }

    body.append(meta, content);
    row.appendChild(body);
    return row;
  }

  #attachCopyHandlers() {
    this.root.querySelectorAll(".copy-message").forEach((button) => {
      button.addEventListener("click", async () => {
        const row = button.closest(".message-row");
        await copyText(row?.dataset.rawContent || "");
        this.toast.show("تم النسخ");
      });
    });

    this.root.querySelectorAll(".copy-code").forEach((button) => {
      button.addEventListener("click", async () => {
        const code = button.closest(".code-block")?.querySelector("code")?.textContent || "";
        await copyText(code);
        button.textContent = "تم النسخ";
        window.setTimeout(() => { button.textContent = "نسخ"; }, 1200);
      });
    });
  }
}
