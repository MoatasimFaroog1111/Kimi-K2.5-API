import { getModelLabel } from "../utils.js";

export class ComposerComponent {
  constructor({ form, input, sendButton, modelSelect }) {
    this.form = form;
    this.input = input;
    this.sendButton = sendButton;
    this.modelSelect = modelSelect;
    this.callbacks = {};
  }

  bind(callbacks) {
    this.callbacks = callbacks;
    this.form.addEventListener("submit", async (event) => {
      event.preventDefault();
      await callbacks.onSubmit?.(this.value);
    });

    this.input.addEventListener("keydown", async (event) => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        await callbacks.onSubmit?.(this.value);
      }
    });

    this.input.addEventListener("input", () => this.resize());
    this.modelSelect.addEventListener("change", () => {
      callbacks.onModelChange?.(this.modelSelect.value);
    });
  }

  get value() {
    return this.input.value.trim();
  }

  setValue(value) {
    this.input.value = value || "";
    this.resize();
  }

  clear() {
    this.setValue("");
  }

  focus() {
    this.input.focus();
  }

  setBusy(isBusy) {
    this.sendButton.disabled = isBusy;
    this.form.classList.toggle("is-sending", isBusy);
  }

  renderModels(models, currentValue) {
    this.modelSelect.replaceChildren();
    if (!models.length) {
      const option = document.createElement("option");
      option.value = currentValue || "";
      option.textContent = currentValue ? getModelLabel(currentValue) : "جاري تحميل النماذج…";
      this.modelSelect.appendChild(option);
      this.modelSelect.disabled = true;
      return;
    }

    this.modelSelect.disabled = false;
    for (const model of models) {
      const option = document.createElement("option");
      option.value = model;
      option.textContent = getModelLabel(model);
      option.selected = model === currentValue;
      this.modelSelect.appendChild(option);
    }
  }

  resize() {
    this.input.style.height = "auto";
    this.input.style.height = `${Math.min(this.input.scrollHeight, 180)}px`;
  }
}
