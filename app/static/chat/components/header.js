export class HeaderComponent {
  constructor({ title, connectionDot, connectionStatus, themeButton, lockButton }) {
    this.title = title;
    this.connectionDot = connectionDot;
    this.connectionStatus = connectionStatus;
    this.themeButton = themeButton;
    this.lockButton = lockButton;
  }

  bind({ onTheme, onLock }) {
    this.themeButton.addEventListener("click", () => onTheme?.());
    this.lockButton.addEventListener("click", () => onLock?.());
  }

  renderTitle(value) {
    this.title.textContent = value || "محادثة جديدة";
    document.title = value && value !== "محادثة جديدة"
      ? `${value} · Kimi Workspace`
      : "Kimi Workspace";
  }

  setConnection(text, type = "pending") {
    this.connectionStatus.textContent = text;
    this.connectionDot.dataset.state = type;
  }
}
