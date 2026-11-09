/// <reference types="vite/client" />
interface ImportMetaEnv {
 readonly VITE_FORM_ENDPOINT?: string;
 readonly VITE_WHATSAPP_NUMBER?: string;
 readonly VITE_TELEGRAM_URL?: string;
 readonly VITE_PLAUSIBLE_DOMAIN?: string;
 readonly VITE_ANALYTICS_SRC?: string;
}
interface ImportMeta { readonly env: ImportMetaEnv }
