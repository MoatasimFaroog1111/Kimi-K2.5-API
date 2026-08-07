export const STORAGE = Object.freeze({
  conversations: "kimi_workspace_conversations_v1",
  activeConversation: "kimi_workspace_active_v1",
  theme: "kimi_workspace_theme_v1",
  sessionKey: "kimi_gateway_key_session_v1",
  rememberedKey: "kimi_gateway_key_local_v1",
});

export const DEFAULT_CONVERSATION_TITLE = "محادثة جديدة";

export const MODEL_LABELS = Object.freeze({
  "kimi-k2.6": "Kimi K2.6",
  "kimi-k2.7-code": "Kimi K2.7 Code",
  "kimi-k2.7-code-highspeed": "Kimi K2.7 Highspeed",
  "kimi-k3": "Kimi K3",
});

export const QUICK_PROMPTS = Object.freeze([
  {
    label: "اكتب كودًا",
    prompt: "ساعدني في بناء ميزة برمجية نظيفة وقابلة للصيانة وفق مبادئ SOLID.",
  },
  {
    label: "حل مشكلة",
    prompt: "سأرسل لك خطأ برمجيًا. حدّد السبب الجذري ثم اقترح إصلاحًا آمنًا قابلًا للاختبار.",
  },
  {
    label: "راجع المشروع",
    prompt: "راجع تصميم مشروعي من ناحية المعمارية والأمان والأداء وقابلية الصيانة.",
  },
  {
    label: "خطط للتنفيذ",
    prompt: "حوّل طلبي إلى خطة تنفيذ قصيرة وواضحة ثم ابدأ من أهم خطوة.",
  },
]);
