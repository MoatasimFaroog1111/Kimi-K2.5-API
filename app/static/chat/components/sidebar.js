import { formatRelativeDate, getModelShortLabel } from "../utils.js";

export class SidebarComponent {
  constructor({ root, backdrop, openButton, closeButton, newButton, searchInput, list, count, exportButton, deleteButton }) {
    this.root = root;
    this.backdrop = backdrop;
    this.openButton = openButton;
    this.closeButton = closeButton;
    this.newButton = newButton;
    this.searchInput = searchInput;
    this.list = list;
    this.count = count;
    this.exportButton = exportButton;
    this.deleteButton = deleteButton;
    this.callbacks = {};
  }

  bind(callbacks) {
    this.callbacks = callbacks;
    this.openButton.addEventListener("click", () => this.open());
    this.closeButton.addEventListener("click", () => this.close());
    this.backdrop.addEventListener("click", () => this.close());
    this.newButton.addEventListener("click", () => callbacks.onNew?.());
    this.searchInput.addEventListener("input", () => callbacks.onSearch?.());
    this.exportButton.addEventListener("click", () => callbacks.onExport?.());
    this.deleteButton.addEventListener("click", () => callbacks.onDelete?.());
  }

  render(conversations, activeId) {
    const query = this.searchInput.value.trim().toLocaleLowerCase("ar");
    const sorted = [...conversations].sort(
      (a, b) => new Date(b.updatedAt) - new Date(a.updatedAt),
    );
    const filtered = query
      ? sorted.filter((item) => item.title.toLocaleLowerCase("ar").includes(query))
      : sorted;

    this.count.textContent = String(conversations.length);
    this.list.replaceChildren();

    if (!filtered.length) {
      const empty = document.createElement("p");
      empty.className = "sidebar-empty";
      empty.textContent = "لا توجد محادثات مطابقة.";
      this.list.appendChild(empty);
      return;
    }

    for (const conversation of filtered) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `conversation-item${conversation.id === activeId ? " active" : ""}`;
      button.dataset.id = conversation.id;
      button.innerHTML = `
        <span class="conversation-name"></span>
        <span class="conversation-meta"></span>
      `;
      button.querySelector(".conversation-name").textContent = conversation.title;
      button.querySelector(".conversation-meta").textContent = `${getModelShortLabel(conversation.model)} · ${formatRelativeDate(conversation.updatedAt)}`;
      button.addEventListener("click", () => this.callbacks.onSelect?.(conversation.id));
      this.list.appendChild(button);
    }
  }

  open() {
    this.root.classList.add("open");
    this.backdrop.classList.add("show");
  }

  close() {
    this.root.classList.remove("open");
    this.backdrop.classList.remove("show");
  }
}
