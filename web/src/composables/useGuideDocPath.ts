import { ref, watch, onMounted, onBeforeUnmount, type Ref } from "vue";

const QUERY_KEY = "doc";
const DEFAULT_DOC = "index";

function readDocFromUrl(): string | null {
  try {
    const url = new URL(window.location.href);
    const value = url.searchParams.get(QUERY_KEY);
    return value?.trim() ? value.trim() : null;
  } catch {
    return null;
  }
}

function writeDocToUrl(path: string): void {
  try {
    const url = new URL(window.location.href);
    const normalized = path.trim() || DEFAULT_DOC;
    if (url.searchParams.get(QUERY_KEY) === normalized) return;
    url.searchParams.set(QUERY_KEY, normalized);
    window.history.replaceState(window.history.state, "", url);
  } catch {
    /* ignore */
  }
}

export function useGuideDocPath(): Ref<string> {
  const docPath = ref(readDocFromUrl() ?? DEFAULT_DOC);

  if (readDocFromUrl() == null) {
    writeDocToUrl(docPath.value);
  }

  watch(docPath, (value) => {
    writeDocToUrl(value);
  });

  function handlePopState(): void {
    const fromUrl = readDocFromUrl();
    if (fromUrl != null && fromUrl !== docPath.value) {
      docPath.value = fromUrl;
    }
  }

  onMounted(() => {
    window.addEventListener("popstate", handlePopState);
  });

  onBeforeUnmount(() => {
    window.removeEventListener("popstate", handlePopState);
  });

  return docPath;
}

/** Resolve a markdown href to a guide doc path (no .md suffix). */
export function guidePathFromHref(href: string, currentDocPath: string): string | null {
  const raw = href.trim();
  if (!raw || raw.startsWith("#")) return null;
  if (/^[a-z][a-z0-9+.-]*:/i.test(raw)) return null;

  let path = raw.replace(/^\//, "").replace(/\.md$/i, "");
  if (path.startsWith("docs/guide/")) {
    path = path.slice("docs/guide/".length);
  }

  if (!path.includes("/") && !path.startsWith("..")) {
    const base = currentDocPath.includes("/")
      ? currentDocPath.slice(0, currentDocPath.lastIndexOf("/") + 1)
      : "";
    path = `${base}${path}`;
  }

  const segments: string[] = [];
  for (const part of path.split("/")) {
    if (part === "" || part === ".") continue;
    if (part === "..") {
      segments.pop();
      continue;
    }
    segments.push(part);
  }
  return segments.join("/") || DEFAULT_DOC;
}
