/**
 * Ed25519 keypair manager for the clinic workstation.
 *
 * Phase 2A of dp4500-host-app-integration-phase2 (Opción A: real
 * capture with WebCrypto + HID WebSdk).
 *
 * Architecture: each clinic workstation has ONE persistent keypair.
 * The private key never leaves the workstation's browser storage; the
 * pubkey is registered with DP4500 on first enroll and used to
 * verify signatures on every subsequent operation. If the operator
 * clears browser storage (IndexedDB), the next enroll generates a
 * new keypair; the previous credential at DP4500 would need a
 * re-enroll. Phase 4 may add key rotation via DP4500's
 * ServiceAPIKey.rotation hook (deferred).
 *
 * Storage backend: IndexedDB (key "dp4500:signing-key:v1"). The
 * private key is stored in non-extractable CryptoKey form via
 * SubtleCrypto so even JS code on the page cannot extract the raw
 * bytes — the key can only be used through the `sign()` call.
 *
 * Canonical string built per DP4500 spec service-biometric-operations:
 *   `<challenge_id>:<user_external_id>:<server_nonce>:<timestamp>`
 * See design §7.2.
 */

const DB_NAME = "dp4500-signing";
const STORE_NAME = "keys";
const KEY_ID = "signing-key-v1";

/** Store the public key bytes alongside the CryptoKey for transmission. */
interface StoredKey {
  privateKey: CryptoKey;
  publicKeyRaw: ArrayBuffer; // 32 raw bytes, Ed25519 public key
  createdAt: number;
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function loadStoredKey(): Promise<StoredKey | null> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readonly");
    const store = tx.objectStore(STORE_NAME);
    const req = store.get(KEY_ID);
    req.onsuccess = () => resolve((req.result as StoredKey) || null);
    req.onerror = () => reject(req.error);
  });
}

async function saveStoredKey(stored: StoredKey): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    const store = tx.objectStore(STORE_NAME);
    const req = store.put(stored, KEY_ID);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}

/** Public key as base64 (URL-safe). The wire contract is plain bytes. */
export function publicKeyToBase64Url(raw: ArrayBuffer): string {
  const bytes = new Uint8Array(raw);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  const b64 = btoa(bin);
  return b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

/** Inverse of {@link publicKeyToBase64Url}. */
export function publicKeyFromBase64Url(b64url: string): ArrayBuffer {
  let b64 = b64url.replace(/-/g, "+").replace(/_/g, "/");
  while (b64.length % 4) b64 += "=";
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}

export interface SigningKey {
  publicKeyRaw: ArrayBuffer;
  createdAt: number;
}

/** Return the workstation's signing keypair, generating it if absent. */
export async function ensureSigningKey(): Promise<SigningKey> {
  const existing = await loadStoredKey();
  if (existing) {
    return { publicKeyRaw: existing.publicKeyRaw, createdAt: existing.createdAt };
  }
  // Generate a fresh Ed25519 keypair. The private key is marked
  // non-extractable so JS code on the page cannot read the raw bytes.
  const keyPair = await crypto.subtle.generateKey(
    { name: "Ed25519" } as EcKeyGenParams & { name: "Ed25519" } as AlgorithmIdentifier,
    /* extractable= */ false,
    ["sign", "verify"],
  );
  const publicKeyRaw = await crypto.subtle.exportKey("raw", keyPair.publicKey);
  const stored: StoredKey = {
    privateKey: keyPair.privateKey,
    publicKeyRaw,
    createdAt: Date.now(),
  };
  await saveStoredKey(stored);
  return { publicKeyRaw, createdAt: stored.createdAt };
}

/**
 * Sign the canonical string used by DP4500's verify endpoint.
 *   canonical = `${challenge_id}:${user_external_id}:${server_nonce}:${timestamp}`
 * Returns the signature as base64 (URL-safe).
 */
export async function signCanonical(
  challenge_id: string,
  user_external_id: string,
  server_nonce: string,
  timestamp: string,
): Promise<string> {
  const existing = await loadStoredKey();
  if (!existing) {
    throw new Error(
      "No signing key loaded; call ensureSigningKey() first.",
    );
  }
  const canonical =
    `${challenge_id}:${user_external_id}:${server_nonce}:${timestamp}`;
  const bytes = new TextEncoder().encode(canonical);
  const sig = await crypto.subtle.sign(
    { name: "Ed25519" } as EcdsaParams & { name: "Ed25519" } as AlgorithmIdentifier,
    existing.privateKey,
    bytes,
  );
  const sigBytes = new Uint8Array(sig);
  let bin = "";
  for (const b of sigBytes) bin += String.fromCharCode(b);
  const b64 = btoa(bin);
  return b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

/** For tests: clear the stored keypair. */
export async function clearSigningKey(): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    const store = tx.objectStore(STORE_NAME);
    const req = store.delete(KEY_ID);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}
