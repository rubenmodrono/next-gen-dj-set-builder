import type { RawTrack } from '../core/types';
import type { LibraryFormat } from './parse';

export interface StoredLibrary {
  name: string;
  format: LibraryFormat | 'demo';
  importedAt: number;
  tracks: RawTrack[];
  skipped: number;
}

const DB = 'set-planifier';
const STORE = 'library';

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function run<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await open();
  try {
    return await new Promise<T>((resolve, reject) => {
      const req = fn(db.transaction(STORE, mode).objectStore(STORE));
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  } finally {
    db.close();
  }
}

/** The library never leaves the browser. IndexedDB can be unavailable (private windows); callers treat failure as "not saved". */
export async function saveLibrary(lib: StoredLibrary): Promise<boolean> {
  try {
    await run('readwrite', (s) => s.put(lib, 'current'));
    return true;
  } catch {
    return false;
  }
}

export async function loadLibrary(): Promise<StoredLibrary | null> {
  try {
    return ((await run('readonly', (s) => s.get('current'))) as StoredLibrary | undefined) ?? null;
  } catch {
    return null;
  }
}

export async function clearLibrary(): Promise<void> {
  try {
    await run('readwrite', (s) => s.delete('current'));
  } catch {
    /* nothing stored */
  }
}
