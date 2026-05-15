/** Secret management and crypto API (profile-scoped). */

export type SecretRecord = {
  profile_code: string;
  secret_name: string;
  secret_type: string;
  secret_data: Record<string, unknown>;
};

export type SecretListResponse = {
  secret_dir: string;
  profile: string;
  secrets: SecretRecord[];
};

export type EncryptResponse = {
  secret_type: string;
  secret_data: Record<string, unknown>;
};

const jsonHeaders = { "Content-Type": "application/json" };

function profileQuery(profile: string): string {
  const q = new URLSearchParams();
  q.set("profile", profile);
  return q.toString();
}

export async function fetchSecretTypes(): Promise<string[]> {
  const r = await fetch("/api/secrets/types");
  if (!r.ok) throw new Error(`secret types: ${r.status}`);
  const data = (await r.json()) as { secret_types: string[] };
  return data.secret_types;
}

export async function fetchSecrets(profile: string): Promise<SecretListResponse> {
  const r = await fetch(`/api/secrets?${profileQuery(profile)}`);
  if (!r.ok) throw new Error(`secrets: ${r.status}`);
  return r.json() as Promise<SecretListResponse>;
}

export async function fetchSecret(profile: string, name: string): Promise<SecretRecord> {
  const r = await fetch(`/api/secrets/${encodeURIComponent(name)}?${profileQuery(profile)}`);
  if (!r.ok) throw new Error(`secret: ${r.status}`);
  return r.json() as Promise<SecretRecord>;
}

export async function saveSecret(
  profile: string,
  name: string,
  secretType: string,
  secretData: Record<string, unknown>,
): Promise<void> {
  const r = await fetch(`/api/secrets/${encodeURIComponent(name)}?${profileQuery(profile)}`, {
    method: "PUT",
    headers: jsonHeaders,
    body: JSON.stringify({ secret_type: secretType, secret_data: secretData }),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `save secret: ${r.status}`);
  }
}

export async function deleteSecret(profile: string, name: string): Promise<void> {
  const r = await fetch(`/api/secrets/${encodeURIComponent(name)}?${profileQuery(profile)}`, {
    method: "DELETE",
  });
  if (!r.ok) throw new Error(`delete secret: ${r.status}`);
}

export async function encryptPlaintext(secretType: string, plaintext: string): Promise<EncryptResponse> {
  const r = await fetch("/api/secrets/crypto/encrypt", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ secret_type: secretType, plaintext }),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `encrypt: ${r.status}`);
  }
  return r.json() as Promise<EncryptResponse>;
}
