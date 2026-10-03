export interface Card {
    id: string
    name: string
    wikiUrl: string
    imageUrl: string
    tags: string[]
    rarity: string
    owned: boolean
}

export interface CollectionGroup {
    name: string
    cards: Card[]
}

const collectionFiles = import.meta.glob<unknown>('../data/*_collection.json', {
    eager: true,
    import: 'default',
})

export function parseCards(data: unknown): Card[] {
    const entries = data && typeof data === 'object' && !Array.isArray(data)
        ? (data as Record<string, unknown>).collection
        : data
    if (!Array.isArray(entries)) throw new Error('Le JSON doit contenir une propriété « collection » avec une liste de cartes.')

    return entries.map((item: unknown, index: number) => {
        if (!item || typeof item !== 'object') throw new Error(`La carte ${index + 1} est invalide.`)
        const entry = item as Record<string, unknown>
        const card = entry.card && typeof entry.card === 'object'
            ? entry.card as Record<string, unknown>
            : entry
        const id = card.id ?? entry.card_id ?? entry.id
        const name = card.wikipedia_title ?? card.name
        const wikiUrl = card.wikipedia_url ?? card.wikiUrl
        const imageUrl = card.hide_image === true ? '' : card.image_url ?? card.imageUrl ?? ''
        const rarity = card.rarity

        for (const [field, value] of Object.entries({ id, name, wikiUrl, rarity })) {
            if (typeof value !== 'string' || !value) {
                throw new Error(`La carte ${index + 1} doit avoir un champ « ${field} » valide.`)
            }
        }

        const rawTags = entry.tags
        if (!Array.isArray(rawTags) || !rawTags.every((tag) => typeof tag === 'string' || (tag && typeof tag === 'object' && typeof (tag as Record<string, unknown>).name === 'string'))) {
            throw new Error(`Les tags de la carte ${index + 1} doivent être une liste de textes ou d’objets avec un nom.`)
        }
        const owned = entry.owned ?? true
        if (typeof owned !== 'boolean') throw new Error(`La carte ${index + 1} doit définir « owned » à true ou false.`)

        return {
            id: id as string,
            name: name as string,
            wikiUrl: wikiUrl as string,
            imageUrl: typeof imageUrl === 'string' ? imageUrl : '',
            tags: [...new Set((rawTags as unknown[]).map((tag) => typeof tag === 'string' ? tag : (tag as Record<string, string>).name).map((tag) => tag.trim()).filter(Boolean))],
            rarity: rarity as string,
            owned,
        }
    })
}

export function loadCollectionCards(): Card[] {
    const cardsById = new Map<string, Card>()

    for (const data of Object.values(collectionFiles)) {
        for (const card of parseCards(data)) {
            const existing = cardsById.get(card.id)
            if (!existing) {
                cardsById.set(card.id, card)
                continue
            }

            existing.tags = [...new Set([...existing.tags, ...card.tags])]
            existing.owned = existing.owned || card.owned
        }
    }

    return [...cardsById.values()]
}

export function groupCards(cards: Card[]): CollectionGroup[] {
    const tagged = new Map<string, Card[]>()
    const untagged: Card[] = []

    for (const card of cards) {
        if (card.tags.length === 0) {
            untagged.push(card)
            continue
        }

        for (const rawTag of card.tags) {
            const tag = rawTag.trim()
            if (!tag) continue
            const key = tag.toLocaleLowerCase('fr')
            const existing = tagged.get(key)
            if (existing) existing.push(card)
            else tagged.set(key, [card])
        }
    }

    const groups = [...tagged.entries()]
        .sort(([first], [second]) => first.localeCompare(second, 'fr', { sensitivity: 'base' }))
        .map(([key, groupCards]) => ({
            name: groupCards[0].tags.find((tag) => tag.toLocaleLowerCase('fr') === key) ?? key,
            cards: groupCards,
        }))

    if (untagged.length > 0) {
        groups.push({
            name: 'Sans catégorie',
            cards: untagged,
        })
    }

    return groups
}