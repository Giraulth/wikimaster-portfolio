import { useMemo, useState } from 'react'
import { groupCards, type Card, type CollectionGroup, loadCollectionCards } from './collection'
import './App.css'

type FilterMode = 'all' | 'owned' | 'wanted'

function rarityTone(rarity: string): string {
  const normalized = rarity.toLocaleLowerCase('fr')
  const tones: Record<string, string> = {
    c: 'c', commun: 'c',
    pc: 'pc', 'peu commun': 'pc',
    r: 'r', rare: 'r',
    sr: 'sr', épique: 'sr',
    ur: 'ur', légendaire: 'ur',
  }

  return tones[normalized] ?? 'other'
}

function CardTile({ card }: { card: Card }) {
  const [imageFailed, setImageFailed] = useState(false)
  const rarityClass = `card-tile--rarity-${rarityTone(card.rarity)}`

  return (
    <article className={`card-tile ${rarityClass}${card.owned ? '' : ' card-tile--wanted'}`}>
      <a className="card-image-link" href={card.wikiUrl} target="_blank" rel="noreferrer">
        <div className={`card-image${imageFailed ? ' card-image--missing' : ''}`}>
          {!imageFailed && card.imageUrl && <img src={card.imageUrl} alt={card.name} loading="lazy" onError={() => setImageFailed(true)} />}
          {(imageFailed || !card.imageUrl) && <span className="image-placeholder">{card.name.slice(0, 1)}</span>}
          <span className={`ownership-stamp${card.owned ? ' ownership-stamp--owned' : ''}`}>
            <span className="stamp-dot" />
            {card.owned ? 'Dans la collection' : 'À trouver'}
          </span>
          <span className="card-number">{card.id}</span>
        </div>
      </a>
      <div className="card-details">
        <div className="card-title-row">
          <h3>{card.name}</h3>
          <span className={`rarity-mark rarity-mark--${rarityTone(card.rarity)}`} title={`Rareté : ${card.rarity}`} aria-label={`Rareté : ${card.rarity}`}>
            {card.rarity}
          </span>
        </div>
        <div className="card-tags">
          {card.tags.map((tag) => <span className="mini-tag" key={tag}>{tag}</span>)}
          {card.tags.length === 0 && <span className="mini-tag mini-tag--quiet">Sans tag</span>}
        </div>
      </div>
    </article>
  )
}

function GroupSection({ group }: { group: CollectionGroup }) {
  return (
    <section className="collection-group" id={`group-${encodeURIComponent(group.name.toLowerCase())}`}>
      <div className="group-heading">
        <div className="group-title-wrap">
          <span className="group-marker" aria-hidden="true" />
          <h2>{group.name}</h2>
        </div>
        <span className="group-count">{String(group.cards.length).padStart(2, '0')} cartes</span>
      </div>
      <div className="card-grid">
        {group.cards.map((card) => <CardTile key={`${group.name}-${card.id}`} card={card} />)}
      </div>
    </section>
  )
}

function readCollection() {
  try {
    return { cards: loadCollectionCards(), error: '' }
  } catch (error) {
    return {
      cards: [],
      error: error instanceof Error ? error.message : 'Un fichier de collection est invalide.',
    }
  }
}

function App() {
  const [collection] = useState(readCollection)
  const [filterMode, setFilterMode] = useState<FilterMode>('all')
  const [selectedCollection, setSelectedCollection] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const { cards, error: loadError } = collection

  const collections = useMemo(() => {
    const counts = new Map<string, { name: string; count: number }>()
    for (const card of cards) {
      for (const tag of card.tags) {
        const key = tag.toLocaleLowerCase('fr')
        const current = counts.get(key)
        if (current) current.count += 1
        else counts.set(key, { name: tag, count: 1 })
      }
    }

    return [...counts.entries()].sort(([first], [second]) => first.localeCompare(second, 'fr', { sensitivity: 'base' }))
  }, [cards])

  const visibleCards = useMemo(() => cards.filter((card) => {
    const matchesMode = filterMode === 'all' || (filterMode === 'owned' ? card.owned : !card.owned)
    const searchText = `${card.name} ${card.tags.join(' ')} ${card.rarity}`.toLocaleLowerCase('fr')
    return matchesMode && searchText.includes(query.trim().toLocaleLowerCase('fr'))
  }), [cards, filterMode, query])

  const groups = useMemo(() => {
    const allGroups = groupCards(visibleCards)
    return selectedCollection
      ? allGroups.filter((group) => group.name.toLocaleLowerCase('fr') === selectedCollection)
      : allGroups
  }, [visibleCards, selectedCollection])
  const ownedCount = cards.filter((card) => card.owned).length
  const completion = cards.length ? Math.round((ownedCount / cards.length) * 100) : 0

  return (
    <main className="portfolio-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Wikimasters, accueil">
          <span className="brand-mark" aria-hidden="true"><span /><span /><span /></span>
          <span className="brand-word">wiki<span>masters</span></span>
        </a>
        <div className="topbar-note"><span className="live-dot" /> COLLECTION PERSONNELLE <span className="topbar-divider">/</span> 2026</div>
        <a className="topbar-link" href="https://www.wikipedia.org/" target="_blank" rel="noreferrer">
          Explorer Wikipedia <span aria-hidden="true">↗</span>
        </a>
      </header>

      <section className="intro" id="top">
        <div className="intro-copy">
          <p className="eyebrow"><span>ARCHIVES VIVANTES</span><span className="eyebrow-line" /></p>
          <h1>Des cartes.<br /><em>Des histoires.</em></h1>
          <p className="intro-description">Une collection de fragments du monde, de celles qu’on garde et de celles qu’on cherche encore.</p>
        </div>
        <div className="collection-stats" aria-label="Statistiques de la collection">
          <div className="stat-block"><span className="stat-number">{String(ownedCount).padStart(2, '0')}</span><span className="stat-label">en collection</span></div>
          <div className="stat-block"><span className="stat-number">{String(cards.length - ownedCount).padStart(2, '0')}</span><span className="stat-label">à découvrir</span></div>
          <div className="stat-progress">
            <div className="progress-copy"><span>Complétée</span><strong>{completion}%</strong></div>
            <div className="progress-track"><span style={{ width: `${completion}%` }} /></div>
          </div>
        </div>
        <div className="intro-index" aria-hidden="true">WM—01</div>
      </section>

      <section className="collection-toolbar" aria-label="Outils de collection">
        <div className="filter-tabs" role="group" aria-label="Filtrer les cartes">
          {([
            ['all', 'Tout'],
            ['owned', 'Possédées'],
            ['wanted', 'À trouver'],
          ] as const).map(([mode, label]) => (
            <button className={filterMode === mode ? 'filter-tab is-active' : 'filter-tab'} key={mode} onClick={() => setFilterMode(mode)} aria-pressed={filterMode === mode}>
              {label}
              {mode === 'all' && <span className="tab-count">{cards.length}</span>}
            </button>
          ))}
        </div>
        <label className="search-box">
          <span className="search-icon" aria-hidden="true" />
          <span className="visually-hidden">Rechercher une carte ou un tag</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Nom, tag, rareté..." />
          {query && <button className="clear-search" onClick={() => setQuery('')} aria-label="Effacer la recherche">×</button>}
        </label>
      </section>
      <div className="quick-filter-bar" role="group" aria-label="Filtrer par collection">
        <span className="quick-filter-heading">Collections</span>
        <div className="quick-filter-list">
          <button
            className={selectedCollection === null ? 'quick-filter-button is-active' : 'quick-filter-button'}
            onClick={() => setSelectedCollection(null)}
            aria-pressed={selectedCollection === null}
          >
            Toutes <span className="quick-filter-count">{cards.length}</span>
          </button>
          {collections.map(([key, collectionTag]) => (
            <button
              className={selectedCollection === key ? 'quick-filter-button is-active' : 'quick-filter-button'}
              key={key}
              onClick={() => setSelectedCollection(key)}
              aria-pressed={selectedCollection === key}
            >
              {collectionTag.name} <span className="quick-filter-count">{collectionTag.count}</span>
            </button>
          ))}
        </div>
      </div>

      {loadError && <div className="status-message status-message--error" role="alert">{loadError}</div>}
      {!loadError && groups.length === 0 && <div className="status-message">Aucune carte ne correspond à cette recherche.</div>}
      {!loadError && groups.map((group) => <GroupSection group={group} key={group.name} />)}

      <footer className="site-footer">
        <span>WIKIMASTERS <span className="footer-slash">/</span> COLLECTION VISUELLE</span>
        <span>Images et biographies via Wikipedia <span aria-hidden="true">↗</span></span>
      </footer>
    </main>
  )
}

export default App
