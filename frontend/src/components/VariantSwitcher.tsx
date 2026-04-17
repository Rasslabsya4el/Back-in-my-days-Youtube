import { useEffect, useState } from "react";

export type VariantId = "a" | "b" | "c";

const STORAGE_KEY = "ytdl.variant";
const COMPARE_KEY = "compare";
const COMPARE_VALUE = "variants";
const VALID: VariantId[] = ["a", "b", "c"];

function readVariantFromUrl(): VariantId | null {
  if (typeof window === "undefined") {
    return null;
  }

  const params = new URLSearchParams(window.location.search);
  const value = params.get("variant");
  if (value && VALID.includes(value as VariantId)) {
    return value as VariantId;
  }

  return null;
}

function readCompareFromUrl() {
  if (typeof window === "undefined") {
    return false;
  }

  const params = new URLSearchParams(window.location.search);
  return params.get(COMPARE_KEY) === COMPARE_VALUE;
}

function readVariantFromStorage(): VariantId | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    if (value && VALID.includes(value as VariantId)) {
      return value as VariantId;
    }
  } catch {
    return null;
  }

  return null;
}

function writeVariantToUrl(id: VariantId) {
  if (typeof window === "undefined") {
    return;
  }

  const url = new URL(window.location.href);
  url.searchParams.set("variant", id);
  window.history.replaceState(null, "", url.toString());
}

function writeCompareToUrl(enabled: boolean) {
  if (typeof window === "undefined") {
    return;
  }

  const url = new URL(window.location.href);
  if (enabled) {
    url.searchParams.set(COMPARE_KEY, COMPARE_VALUE);
  } else {
    url.searchParams.delete(COMPARE_KEY);
  }
  window.history.replaceState(null, "", url.toString());
}

export function useVariant(): [VariantId, (id: VariantId) => void] {
  const [id, setId] = useState<VariantId>(() => readVariantFromUrl() ?? readVariantFromStorage() ?? "a");

  useEffect(() => {
    writeVariantToUrl(id);
    try {
      window.localStorage.setItem(STORAGE_KEY, id);
    } catch {
      return;
    }
  }, [id]);

  useEffect(() => {
    const handler = () => {
      const fromUrl = readVariantFromUrl();
      if (fromUrl && fromUrl !== id) {
        setId(fromUrl);
      }
    };

    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  }, [id]);

  return [id, setId];
}

export function useCompareMode(): [boolean, (enabled: boolean) => void] {
  const [compareMode, setCompareMode] = useState(readCompareFromUrl);

  useEffect(() => {
    writeCompareToUrl(compareMode);
  }, [compareMode]);

  useEffect(() => {
    const handler = () => {
      setCompareMode(readCompareFromUrl());
    };

    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  }, []);

  return [compareMode, setCompareMode];
}

export function VariantSwitcher({
  value,
  onChange,
}: {
  value: VariantId;
  onChange: (id: VariantId) => void;
}) {
  return (
    <div
      aria-label="Layout variant"
      className="variant-switcher"
      role="group"
      title="Preview-only single-layout switcher"
    >
      <span className="vs-label">Variant</span>
      {VALID.map((id) => (
        <button
          key={id}
          aria-pressed={value === id}
          className={value === id ? "active" : ""}
          onClick={() => onChange(id)}
          title={`Switch to variant ${id.toUpperCase()}`}
          type="button"
        >
          {id.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
