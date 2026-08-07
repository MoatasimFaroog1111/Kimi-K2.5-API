import { ChatApi } from "./api.js";
import { AuthComponent } from "./components/auth.js";
import { ComposerComponent } from "./components/composer.js";
import { HeaderComponent } from "./components/header.js";
import { MessagesComponent } from "./components/messages.js";
import { SidebarComponent } from "./components/sidebar.js";
import { ToastComponent } from "./components/toast.js";
import { ChatController } from "./controller.js";
import { ChatStore } from "./store.js";

function boot() {
  const toast = new ToastComponent(document.getElementById("toast"));
  const store = new ChatStore();
  const api = new ChatApi();

  const auth = new AuthComponent({
    overlay: document.getElementById("authOverlay"),
    form: document.getElementById("authForm"),
    input: document.getElementById("gatewayKey"),
    remember: document.getElementById("rememberKey"),
    toggle: document.getElementById("toggleSecret"),
    error: document.getElementById("authError"),
    submit: document.getElementById("authSubmit"),
    appShell: document.getElementById("appShell"),
  });

  const sidebar = new SidebarComponent({
    root: document.getElementById("sidebar"),
    backdrop: document.getElementById("sidebarBackdrop"),
    openButton: document.getElementById("openSidebar"),
    closeButton: document.getElementById("closeSidebar"),
    newButton: document.getElementById("newChatButton"),
    searchInput: document.getElementById("conversationSearch"),
    list: document.getElementById("conversationList"),
    count: document.getElementById("conversationCount"),
    exportButton: document.getElementById("exportButton"),
    deleteButton: document.getElementById("deleteButton"),
  });

  const header = new HeaderComponent({
    title: document.getElementById("conversationTitle"),
    connectionDot: document.getElementById("connectionDot"),
    connectionStatus: document.getElementById("connectionStatus"),
    themeButton: document.getElementById("themeButton"),
    lockButton: document.getElementById("lockButton"),
  });

  const messages = new MessagesComponent(
    document.getElementById("messages"),
    toast,
  );

  const composer = new ComposerComponent({
    form: document.getElementById("composer"),
    input: document.getElementById("messageInput"),
    sendButton: document.getElementById("sendButton"),
    modelSelect: document.getElementById("modelSelect"),
  });

  const controller = new ChatController({
    store,
    api,
    auth,
    sidebar,
    header,
    messages,
    composer,
    toast,
  });

  controller.initialize();
  window.kimiChat = Object.freeze({ controller, store });
}

if (document.readyState === "loading") {
  window.addEventListener("DOMContentLoaded", boot, { once: true });
} else {
  boot();
}
