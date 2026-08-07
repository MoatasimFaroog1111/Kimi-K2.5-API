export class AuthComponent {
  constructor({ overlay, form, input, remember, toggle, error, submit, appShell }) {
    this.overlay = overlay;
    this.form = form;
    this.input = input;
    this.remember = remember;
    this.toggle = toggle;
    this.error = error;
    this.submit = submit;
    this.appShell = appShell;
  }

  bind({ onSubmit }) {
    this.form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const key = this.input.value.trim();
      if (!key) {
        this.setError("أدخل مفتاح الدخول أولًا.");
        return;
      }
      await onSubmit(key, this.remember.checked);
    });

    this.toggle.addEventListener("click", () => {
      this.input.type = this.input.type === "password" ? "text" : "password";
      this.toggle.setAttribute(
        "aria-label",
        this.input.type === "password" ? "إظهار المفتاح" : "إخفاء المفتاح",
      );
    });
  }

  show(message = "") {
    this.appShell.classList.add("is-locked");
    this.overlay.classList.remove("hidden");
    this.setError(message);
    window.setTimeout(() => this.input.focus(), 60);
  }

  hide() {
    this.overlay.classList.add("hidden");
    this.appShell.classList.remove("is-locked");
    this.input.value = "";
    this.setError("");
  }

  setBusy(isBusy) {
    this.submit.disabled = isBusy;
    this.input.disabled = isBusy;
    const label = this.submit.querySelector("span");
    if (label) label.textContent = isBusy ? "جاري التحقق…" : "متابعة";
  }

  setError(message) {
    this.error.textContent = message || "";
  }
}
