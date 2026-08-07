export class ToastComponent {
  constructor(element) {
    this.element = element;
    this.timer = null;
  }

  show(message, duration = 3000) {
    window.clearTimeout(this.timer);
    this.element.textContent = message;
    this.element.classList.add("show");
    this.timer = window.setTimeout(() => this.element.classList.remove("show"), duration);
  }
}
