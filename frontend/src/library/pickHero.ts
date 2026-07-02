import type { LibraryItemView } from './libraryApi'

/** Most recently active book (hero); ties broken by id for determinism. */
export function pickHero(items: LibraryItemView[]): LibraryItemView | null {
  const started = items.filter((item) => item.progress !== null)
  if (started.length === 0) return null
  return [...started].sort((a, b) => {
    const at = a.progress ? Date.parse(a.progress.updated_at) : 0
    const bt = b.progress ? Date.parse(b.progress.updated_at) : 0
    return bt - at || a.id.localeCompare(b.id)
  })[0]
}
