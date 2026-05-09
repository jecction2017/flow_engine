export type ProfilesResponse = {
  profiles: string[];
};

export type ProfileConfigResponse = {
  default_profile: string;
  profiles: string[];
};

const jsonHeaders = { "Content-Type": "application/json" };

export async function fetchProfiles(): Promise<ProfilesResponse> {
  const r = await fetch("/api/profiles");
  if (!r.ok) throw new Error(`profiles: ${r.status}`);
  return r.json() as Promise<ProfilesResponse>;
}

export async function createProfile(profile: string): Promise<void> {
  const r = await fetch("/api/profiles", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ profile }),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `create profile: ${r.status}`);
  }
}

export async function fetchProfileConfig(): Promise<ProfileConfigResponse> {
  const r = await fetch("/api/profiles/config");
  if (!r.ok) throw new Error(`profile config: ${r.status}`);
  return r.json() as Promise<ProfileConfigResponse>;
}

export async function saveDefaultProfile(defaultProfile: string): Promise<void> {
  const r = await fetch("/api/profiles/config", {
    method: "PUT",
    headers: jsonHeaders,
    body: JSON.stringify({ default_profile: defaultProfile }),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `save profile config: ${r.status}`);
  }
}

export type ProfileSystemPolicyResponse = {
  profile: string;
  /** 与 ``CapabilityRule.model_dump()`` 同形 — 后端做 Pydantic 校验。 */
  system_capability_policy: Record<string, unknown>;
};

export type SystemDefaultCapabilityPolicyResponse = {
  debug: Record<string, unknown>[];
  shadow: Record<string, unknown>[];
  production: Record<string, unknown>[];
};

export async function fetchSystemDefaultCapabilityPolicy(): Promise<SystemDefaultCapabilityPolicyResponse> {
  const r = await fetch("/api/capabilities/system-default-policy");
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `system default policy: ${r.status}`);
  }
  return r.json() as Promise<SystemDefaultCapabilityPolicyResponse>;
}

export async function fetchProfileSystemPolicy(
  profile: string,
): Promise<ProfileSystemPolicyResponse> {
  const r = await fetch(`/api/profiles/${encodeURIComponent(profile)}/system-policy`);
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `system policy: ${r.status}`);
  }
  return r.json() as Promise<ProfileSystemPolicyResponse>;
}

export async function saveProfileSystemPolicy(
  profile: string,
  policy: Record<string, unknown>,
): Promise<ProfileSystemPolicyResponse> {
  const r = await fetch(`/api/profiles/${encodeURIComponent(profile)}/system-policy`, {
    method: "PUT",
    headers: jsonHeaders,
    body: JSON.stringify({ system_capability_policy: policy }),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `save system policy: ${r.status}`);
  }
  return r.json() as Promise<ProfileSystemPolicyResponse>;
}
