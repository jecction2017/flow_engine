import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import "./styles/global.css";
import "./styles/run-trace.css";

createApp(App).use(createPinia()).mount("#app");
