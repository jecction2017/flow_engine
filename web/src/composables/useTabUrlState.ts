import { ref, watch, onMounted, onBeforeUnmount, type Ref } from "vue";

interface UseTabUrlStateOptions<T extends string> {
  defaultValue: T;
  allowedValues: readonly T[];
  queryKey?: string;
  sessionStorageKey?: string;
}

function safeReadFromUrl<T extends string>(queryKey: string, allowed: Set<T>): T | null {
  try {
    const url = new URL(window.location.href);
    const value = url.searchParams.get(queryKey);
    if (!value) return null;
    return allowed.has(value as T) ? (value as T) : null;
  } catch {
    return null;
  }
}

function safeWriteToUrl<T extends string>(queryKey: string, value: T): void {
  try {
    const url = new URL(window.location.href);
    if (url.searchParams.get(queryKey) === value) return;
    url.searchParams.set(queryKey, value);
    window.history.replaceState(window.history.state, "", url);
  } catch {
    /* ignore */
  }
}

function safeReadFromSession<T extends string>(storageKey: string, allowed: Set<T>): T | null {
  try {
    const value = sessionStorage.getItem(storageKey);
    if (!value) return null;
    return allowed.has(value as T) ? (value as T) : null;
  } catch {
    return null;
  }
}

function safeWriteToSession<T extends string>(storageKey: string, value: T): void {
  try {
    sessionStorage.setItem(storageKey, value);
  } catch {
    /* ignore */
  }
}

export function useTabUrlState<T extends string>(options: UseTabUrlStateOptions<T>): Ref<T> {
  const queryKey = options.queryKey ?? "tab";
  const sessionStorageKey = options.sessionStorageKey ?? `tab:${queryKey}`;
  const allowedValues = new Set(options.allowedValues);

  const state = ref<T>(
    safeReadFromUrl(queryKey, allowedValues) ??
      safeReadFromSession(sessionStorageKey, allowedValues) ??
      options.defaultValue,
  );

  safeWriteToUrl(queryKey, state.value);
  safeWriteToSession(sessionStorageKey, state.value);

  watch(state, (value) => {
    safeWriteToUrl(queryKey, value);
    safeWriteToSession(sessionStorageKey, value);
  });

  function handlePopState(): void {
    const fromUrl = safeReadFromUrl(queryKey, allowedValues);
    if (fromUrl && fromUrl !== state.value) {
      state.value = fromUrl;
    }
  }

  onMounted(() => {
    window.addEventListener("popstate", handlePopState);
  });

  onBeforeUnmount(() => {
    window.removeEventListener("popstate", handlePopState);
  });

  return state;
}
