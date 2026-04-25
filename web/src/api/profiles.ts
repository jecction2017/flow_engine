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
